"""Pydantic schemas for the predictions router."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.models.prediction import RiskTier


class ModelVersionSummary(BaseModel):
    id: uuid.UUID
    version_name: str
    algorithm: str
    is_active: bool
    training_rows: int | None = None
    auc_roc: Decimal | None = None
    accuracy: Decimal | None = None
    precision_score: Decimal | None = None
    recall_score: Decimal | None = None
    f1_score: Decimal | None = None
    feature_importance: dict[str, Any] | None = None
    trained_at: datetime

    model_config = {"from_attributes": True}


class RiskDistribution(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class PredictionRunResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    scored: int
    model_version_id: uuid.UUID
    model_version_name: str
    risk_distribution: RiskDistribution


class TopFactor(BaseModel):
    feature: str
    shap_value: float
    direction: str        # "positive" (increases churn risk) | "negative" (reduces)
    feature_value: float
    description: str


class CustomerPredictionResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    model_version_id: uuid.UUID
    churn_probability: Decimal
    risk_tier: RiskTier
    predicted_at: datetime
    shap_values: dict[str, float] | None = None
    top_factors: list[TopFactor] | None = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}
