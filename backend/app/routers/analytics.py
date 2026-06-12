"""Analytics router — snapshot creation, history, and live summary."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.analytics import AnalyticsSnapshot
from app.models.user import User
from app.schemas.analytics import SnapshotListResponse, SnapshotResponse
from app.services.analytics import compute_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# POST /snapshot — compute and upsert today's snapshot
# ---------------------------------------------------------------------------
@router.post("/snapshot", response_model=SnapshotResponse)
async def create_snapshot(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticsSnapshot:
    """Compute today's analytics snapshot and upsert it into the DB."""
    today = date.today()
    fresh = await compute_snapshot(db, current_user, snapshot_date=today)

    # Upsert: unique constraint on (user_id, snapshot_date)
    existing_result = await db.execute(
        select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.user_id == current_user.id,
            AnalyticsSnapshot.snapshot_date == today,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.total_customers       = fresh.total_customers
        existing.active_customers      = fresh.active_customers
        existing.churned_this_period   = fresh.churned_this_period
        existing.churn_rate            = fresh.churn_rate
        existing.mrr                   = fresh.mrr
        existing.mrr_at_risk           = fresh.mrr_at_risk
        existing.avg_churn_probability = fresh.avg_churn_probability
        existing.critical_risk_count   = fresh.critical_risk_count
        existing.high_risk_count       = fresh.high_risk_count
        existing.medium_risk_count     = fresh.medium_risk_count
        existing.low_risk_count        = fresh.low_risk_count
        await db.flush()
        await db.refresh(existing)
        logger.info("Updated snapshot for user %s on %s", current_user.id, today)
        return existing
    else:
        db.add(fresh)
        await db.flush()
        await db.refresh(fresh)
        logger.info("Created snapshot for user %s on %s", current_user.id, today)
        return fresh


# ---------------------------------------------------------------------------
# GET /snapshots — paginated history for trend charts
# ---------------------------------------------------------------------------
@router.get("/snapshots", response_model=SnapshotListResponse)
async def list_snapshots(
    limit: int = Query(default=90, ge=1, le=365),
    skip: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SnapshotListResponse:
    """Return stored snapshots ordered newest-first (for trend charts)."""
    count_result = await db.execute(
        select(func.count()).select_from(AnalyticsSnapshot).where(
            AnalyticsSnapshot.user_id == current_user.id
        )
    )
    total = count_result.scalar_one()

    rows_result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.user_id == current_user.id)
        .order_by(AnalyticsSnapshot.snapshot_date.desc())
        .offset(skip)
        .limit(limit)
    )
    snapshots = list(rows_result.scalars().all())

    return SnapshotListResponse(
        snapshots=[SnapshotResponse.model_validate(s) for s in snapshots],
        total=total,
    )


# ---------------------------------------------------------------------------
# GET /summary — latest snapshot or computed on-the-fly
# ---------------------------------------------------------------------------
@router.get("/summary", response_model=SnapshotResponse)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SnapshotResponse:
    """Return today's snapshot if it exists; otherwise compute it live (read-only)."""
    today = date.today()

    # Try today's snapshot first
    latest_result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.user_id == current_user.id)
        .order_by(AnalyticsSnapshot.snapshot_date.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()

    if latest and latest.snapshot_date == today:
        return SnapshotResponse.model_validate(latest)

    # Compute live (not persisted — caller should POST /snapshot to save it)
    live = await compute_snapshot(db, current_user, snapshot_date=today)
    return SnapshotResponse.model_validate(live)
