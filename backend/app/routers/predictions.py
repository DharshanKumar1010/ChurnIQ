"""Predictions router — model registry, batch scoring, per-customer lookup."""

import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.customer import Customer
from app.models.prediction import ChurnPrediction, ModelVersion, RiskTier
from app.models.user import User
from app.schemas.prediction import (
    CustomerPredictionResponse,
    ModelVersionSummary,
    PredictionRunResponse,
    RiskDistribution,
)
from app.services.ml.explainability import build_shap_dict, build_top_factors, compute_shap
from app.services.ml.features import build_features
from app.services.ml.training import _ARTIFACT_ROOT

logger = logging.getLogger(__name__)
router = APIRouter()

# churn_probability → risk tier (highest threshold wins)
_THRESHOLDS: list[tuple[float, RiskTier]] = [
    (0.75, RiskTier.critical),
    (0.50, RiskTier.high),
    (0.30, RiskTier.medium),
    (0.00, RiskTier.low),
]


def _assign_tier(prob: float) -> RiskTier:
    for threshold, tier in _THRESHOLDS:
        if prob >= threshold:
            return tier
    return RiskTier.low


def _customers_to_df(customers: list[Customer]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "signup_date": c.signup_date,
            "last_activity_date": c.last_activity_date,
            "logins_last_30d": c.logins_last_30d,
            "monthly_revenue": float(c.monthly_revenue),
            "support_tickets_open": c.support_tickets_open,
            "support_tickets_total": c.support_tickets_total,
            "billing_issues_count": c.billing_issues_count,
            "nps_score": c.nps_score,
            "feature_usage_score": (
                float(c.feature_usage_score) if c.feature_usage_score is not None else None
            ),
            "contract_length_months": c.contract_length_months,
            "contract_end_date": c.contract_end_date,
            "plan": c.plan.value,
            "company_size": c.company_size,
        }
        for c in customers
    ])


# ---------------------------------------------------------------------------
# GET /model-versions
# ---------------------------------------------------------------------------
@router.get("/model-versions", response_model=list[ModelVersionSummary])
async def list_model_versions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ModelVersion]:
    """List all trained model versions, newest first."""
    result = await db.execute(
        select(ModelVersion).order_by(ModelVersion.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------
@router.post("/run", response_model=PredictionRunResponse)
async def run_predictions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PredictionRunResponse:
    """Score all current user's customers with the active model and upsert results."""
    # Resolve active model
    mv_result = await db.execute(
        select(ModelVersion).where(ModelVersion.is_active.is_(True))
    )
    active = mv_result.scalar_one_or_none()
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active model found. Train one via `python ml/train.py`.",
        )
    if not active.model_artifact_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Active model has no artifact path — retrain required.",
        )

    # Resolve artifact — stored path may be from a different host (e.g. local Windows path
    # when running in Docker on Linux). Fall back to _ARTIFACT_ROOT/<version>/pipeline.joblib.
    artifact_path = Path(active.model_artifact_path)
    if not artifact_path.exists():
        fallback = _ARTIFACT_ROOT / active.version_name / "pipeline.joblib"
        if not fallback.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Model artifact not found. Tried: {artifact_path} and {fallback}. "
                    "Re-deploy with model files included or retrain."
                ),
            )
        artifact_path = fallback
        logger.info("Using fallback artifact path: %s", artifact_path)
    pipeline = joblib.load(artifact_path)

    # Load current user's customers
    cust_result = await db.execute(
        select(Customer).where(Customer.user_id == current_user.id)
    )
    customers = list(cust_result.scalars().all())
    if not customers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No customers found — import customers before running predictions.",
        )

    # Build feature matrix, score, compute SHAP in one pass
    X = build_features(_customers_to_df(customers), reference_date=date.today())
    probabilities: np.ndarray = pipeline.predict_proba(X)[:, 1]
    shap_result = compute_shap(pipeline, X)

    # Load existing predictions for this model+user (upsert support)
    customer_ids = [c.id for c in customers]
    existing_result = await db.execute(
        select(ChurnPrediction).where(
            ChurnPrediction.model_version_id == active.id,
            ChurnPrediction.customer_id.in_(customer_ids),
        )
    )
    existing: dict[uuid.UUID, ChurnPrediction] = {
        p.customer_id: p for p in existing_result.scalars().all()
    }

    now = datetime.now(timezone.utc)
    risk_counts: dict[str, int] = {t.value: 0 for t in RiskTier}

    for idx, (customer, prob) in enumerate(zip(customers, probabilities)):
        prob_val = round(float(prob), 4)
        tier = _assign_tier(prob_val)
        risk_counts[tier.value] += 1

        shap_dict = build_shap_dict(shap_result.shap_matrix[idx])
        top_factors = build_top_factors(
            shap_result.shap_matrix[idx],
            shap_result.X_imputed[idx],
        )

        if customer.id in existing:
            p = existing[customer.id]
            p.churn_probability = prob_val  # type: ignore[assignment]
            p.risk_tier = tier
            p.predicted_at = now
            p.shap_values = shap_dict
            p.top_factors = top_factors
        else:
            db.add(ChurnPrediction(
                customer_id=customer.id,
                model_version_id=active.id,
                churn_probability=prob_val,
                risk_tier=tier,
                predicted_at=now,
                shap_values=shap_dict,
                top_factors=top_factors,
            ))

    await db.flush()
    logger.info(
        "Scored %d customers with model '%s' (SHAP included): %s",
        len(customers), active.version_name, risk_counts,
    )

    return PredictionRunResponse(
        scored=len(customers),
        model_version_id=active.id,
        model_version_name=active.version_name,
        risk_distribution=RiskDistribution(**risk_counts),
    )


# ---------------------------------------------------------------------------
# GET /{customer_id}
# ---------------------------------------------------------------------------
@router.get("/{customer_id}", response_model=CustomerPredictionResponse)
async def get_customer_prediction(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChurnPrediction:
    """Return the latest prediction for a single customer (scoped to current user)."""
    # Verify customer ownership
    cust_result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.user_id == current_user.id,
        )
    )
    if cust_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # Latest prediction by predicted_at
    pred_result = await db.execute(
        select(ChurnPrediction)
        .where(ChurnPrediction.customer_id == customer_id)
        .order_by(ChurnPrediction.predicted_at.desc())
        .limit(1)
    )
    prediction = pred_result.scalar_one_or_none()
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No predictions found for this customer. Run POST /predictions/run first.",
        )
    return prediction
