"""Analytics snapshot computation.

compute_snapshot(db, user, snapshot_date) → AnalyticsSnapshot (not yet persisted)

All metrics derive from the user's customers + their latest ChurnPrediction rows.
The caller is responsible for persisting / upserting the returned object.
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsSnapshot
from app.models.customer import Customer
from app.models.prediction import ChurnPrediction, RiskTier
from app.models.user import User

logger = logging.getLogger(__name__)

_PERIOD_DAYS = 30
_AT_RISK_TIERS = {RiskTier.high, RiskTier.critical}


async def compute_snapshot(
    db: AsyncSession,
    user: User,
    snapshot_date: date | None = None,
) -> AnalyticsSnapshot:
    """Compute analytics metrics for *user* as of *snapshot_date*.

    Returns an unsaved AnalyticsSnapshot ORM object.  The caller must add it to
    the session and commit (or upsert into an existing row).
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    period_start = snapshot_date - timedelta(days=_PERIOD_DAYS)

    # ------------------------------------------------------------------ #
    # 1. Customer metrics                                                  #
    # ------------------------------------------------------------------ #
    cust_result = await db.execute(
        select(Customer).where(Customer.user_id == user.id)
    )
    customers = list(cust_result.scalars().all())
    customer_map: dict[uuid.UUID, Customer] = {c.id: c for c in customers}

    total = len(customers)
    active_count = sum(1 for c in customers if not c.is_churned)
    churned_all = total - active_count

    # churned_this_period: churned with churned_at in window; if churned_at is
    # null and is_churned=True, attribute to current period (data gap).
    churned_this_period = sum(
        1 for c in customers
        if c.is_churned and (c.churned_at is None or c.churned_at >= period_start)
    )

    churn_rate: Decimal | None = (
        round(Decimal(churned_all) / Decimal(total), 4) if total > 0 else None
    )
    mrr = round(
        sum(float(c.monthly_revenue) for c in customers if not c.is_churned),
        2,
    )

    # ------------------------------------------------------------------ #
    # 2. Prediction-based metrics (latest prediction per customer)        #
    # ------------------------------------------------------------------ #
    latest_preds: dict[uuid.UUID, ChurnPrediction] = {}
    if customer_map:
        pred_result = await db.execute(
            select(ChurnPrediction).where(
                ChurnPrediction.customer_id.in_(list(customer_map.keys()))
            )
        )
        for p in pred_result.scalars().all():
            existing = latest_preds.get(p.customer_id)
            if existing is None or p.predicted_at > existing.predicted_at:
                latest_preds[p.customer_id] = p

    probs = [float(p.churn_probability) for p in latest_preds.values()]
    avg_prob: Decimal | None = (
        round(Decimal(sum(probs) / len(probs)), 4) if probs else None
    )

    risk_counts: dict[str, int] = {t.value: 0 for t in RiskTier}
    for p in latest_preds.values():
        risk_counts[p.risk_tier.value] += 1

    # MRR at risk: revenue of non-churned customers whose latest pred is high/critical
    at_risk_ids = {
        p.customer_id
        for p in latest_preds.values()
        if p.risk_tier in _AT_RISK_TIERS
    }
    mrr_at_risk = round(
        sum(
            float(customer_map[cid].monthly_revenue)
            for cid in at_risk_ids
            if cid in customer_map and not customer_map[cid].is_churned
        ),
        2,
    )

    logger.info(
        "Snapshot computed for user %s: total=%d active=%d churn_rate=%.2f%% "
        "MRR=%.0f MRR_at_risk=%.0f critical=%d high=%d",
        user.id, total, active_count,
        float(churn_rate or 0) * 100,
        mrr, mrr_at_risk,
        risk_counts[RiskTier.critical.value],
        risk_counts[RiskTier.high.value],
    )

    return AnalyticsSnapshot(
        user_id=user.id,
        snapshot_date=snapshot_date,
        total_customers=total,
        active_customers=active_count,
        churned_this_period=churned_this_period,
        churn_rate=churn_rate,
        mrr=Decimal(str(mrr)),
        mrr_at_risk=Decimal(str(mrr_at_risk)),
        avg_churn_probability=avg_prob,
        critical_risk_count=risk_counts[RiskTier.critical.value],
        high_risk_count=risk_counts[RiskTier.high.value],
        medium_risk_count=risk_counts[RiskTier.medium.value],
        low_risk_count=risk_counts[RiskTier.low.value],
    )
