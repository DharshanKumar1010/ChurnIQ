import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

import enum


class RiskTier(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    algorithm: Mapped[str] = mapped_column(String, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    training_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auc_roc: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    precision_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    recall_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    f1_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    feature_names: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feature_importance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    predictions: Mapped[list["ChurnPrediction"]] = relationship(
        "ChurnPrediction", back_populates="model_version"
    )


class ChurnPrediction(Base):
    __tablename__ = "churn_predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    churn_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    risk_tier: Mapped[RiskTier] = mapped_column(
        Enum(RiskTier, name="risk_tier"), nullable=False
    )
    shap_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    top_factors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="predictions"
    )
    model_version: Mapped["ModelVersion"] = relationship(
        "ModelVersion", back_populates="predictions"
    )