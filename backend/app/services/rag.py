"""RAG helpers for the churn chatbot.

build_context(db, user) → str    — assembles analytics + top-risk data as plain text
ask_llm(context, question) → str — sends context+question to the configured LLM
"""

import logging
from datetime import date

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.customer import Customer
from app.models.prediction import ChurnPrediction, ModelVersion, RiskTier
from app.models.user import User
from app.services.analytics import compute_snapshot

logger = logging.getLogger(__name__)
settings = get_settings()

_AT_RISK = {RiskTier.high, RiskTier.critical}
_TOP_N_CUSTOMERS = 10

_SYSTEM_PROMPT = (
    "You are a churn analytics assistant for ChurnIQ. "
    "Answer questions using ONLY the context provided below — do not invent data. "
    "Be concise and specific: cite customer names, percentages, and dollar amounts "
    "from the context. If the context doesn't contain enough information to answer, "
    "say so briefly rather than guessing."
)


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------
async def build_context(db: AsyncSession, user: User) -> str:
    """Return a text block summarising the user's churn data for the LLM."""
    lines: list[str] = []

    # ── Analytics snapshot ────────────────────────────────────────────────
    snap = await compute_snapshot(db, user, snapshot_date=date.today())

    churn_pct = float(snap.churn_rate or 0) * 100
    mrr = float(snap.mrr or 0)
    at_risk_mrr = float(snap.mrr_at_risk or 0)
    at_risk_pct = (at_risk_mrr / mrr * 100) if mrr else 0
    avg_prob = float(snap.avg_churn_probability or 0) * 100

    lines += [
        "=== CHURN ANALYTICS SUMMARY ===",
        f"Date: {snap.snapshot_date}",
        f"Total customers: {snap.total_customers} | "
        f"Active: {snap.active_customers} | "
        f"Churned: {snap.total_customers - snap.active_customers}",
        f"Churn rate: {churn_pct:.1f}%",
        f"New churns (last 30 days): {snap.churned_this_period}",
        f"MRR (active): ${mrr:,.0f}/mo",
        f"MRR at risk (high+critical tier): ${at_risk_mrr:,.0f}/mo ({at_risk_pct:.1f}% of MRR)",
        f"Avg predicted churn probability: {avg_prob:.1f}%",
        f"Risk distribution — Critical: {snap.critical_risk_count} | "
        f"High: {snap.high_risk_count} | "
        f"Medium: {snap.medium_risk_count} | "
        f"Low: {snap.low_risk_count}",
        "",
    ]

    # ── Active model ──────────────────────────────────────────────────────
    mv_result = await db.execute(
        select(ModelVersion).where(ModelVersion.is_active.is_(True))
    )
    active_model = mv_result.scalar_one_or_none()
    if active_model:
        top_feats = [
            k for k, _ in sorted(
                (active_model.feature_importance or {}).items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]
        ]
        lines += [
            "=== ACTIVE PREDICTION MODEL ===",
            f"Version: {active_model.version_name} ({active_model.algorithm.upper()})",
            f"Trained on: {active_model.training_rows} customers",
            f"AUC-ROC: {float(active_model.auc_roc or 0):.4f} | "
            f"F1: {float(active_model.f1_score or 0):.4f} | "
            f"Recall: {float(active_model.recall_score or 0):.4f}",
            f"Top churn drivers (feature importance): {', '.join(top_feats)}",
            "",
        ]

    # ── Top at-risk customers ─────────────────────────────────────────────
    cust_result = await db.execute(
        select(Customer).where(Customer.user_id == user.id)
    )
    customers = list(cust_result.scalars().all())
    customer_map = {c.id: c for c in customers}

    pred_result = await db.execute(
        select(ChurnPrediction).where(
            ChurnPrediction.customer_id.in_(list(customer_map.keys()))
        )
    )
    # Latest prediction per customer
    latest: dict = {}
    for p in pred_result.scalars().all():
        ex = latest.get(p.customer_id)
        if ex is None or p.predicted_at > ex.predicted_at:
            latest[p.customer_id] = p

    # Sort by probability desc, take top N from high/critical tiers
    at_risk_preds = sorted(
        (p for p in latest.values() if p.risk_tier in _AT_RISK),
        key=lambda p: float(p.churn_probability),
        reverse=True,
    )[:_TOP_N_CUSTOMERS]

    if at_risk_preds:
        lines.append(f"=== TOP {len(at_risk_preds)} AT-RISK CUSTOMERS ===")
        for i, pred in enumerate(at_risk_preds, 1):
            cust = customer_map.get(pred.customer_id)
            if not cust:
                continue
            prob_pct = float(pred.churn_probability) * 100
            rev = float(cust.monthly_revenue)
            lines.append(
                f"{i}. {cust.name} | tier={pred.risk_tier.value} | "
                f"prob={prob_pct:.1f}% | plan={cust.plan.value} | ${rev:.0f}/mo | "
                f"churned={cust.is_churned}"
            )
            factors = pred.top_factors or []
            for f in factors[:3]:
                arrow = "+" if f.get("direction") == "positive" else "-"
                lines.append(
                    f"   [{arrow}{abs(f['shap_value']):.3f}] {f['feature']}: {f['description']}"
                )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------
async def ask_llm(context: str, question: str) -> str:
    """Send context + question to the LLM and return the reply text."""
    if not settings.OPENAI_API_KEY:
        return "LLM not configured — set OPENAI_API_KEY in .env."

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

    user_content = f"CONTEXT:\n{context}\n\nQUESTION: {question}"

    logger.info("LLM request: model=%s question=%r", settings.OPENAI_MODEL, question[:80])
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    reply = response.choices[0].message.content or ""
    logger.info("LLM response: %d chars", len(reply))
    return reply
