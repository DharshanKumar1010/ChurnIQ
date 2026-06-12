import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

import enum


class PlanType(str, enum.Enum):
    free = "free"
    starter = "starter"
    growth = "growth"
    enterprise = "enterprise"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)

    # Subscription
    plan: Mapped[PlanType] = mapped_column(
        Enum(PlanType, name="plan_type"), nullable=False, default=PlanType.starter
    )
    monthly_revenue: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )
    contract_length_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signup_date: Mapped[date] = mapped_column(Date, nullable=False)
    contract_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Engagement signals
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    logins_last_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feature_usage_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    support_tickets_open: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    support_tickets_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nps_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    billing_issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Firmographics
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    company_size: Mapped[str | None] = mapped_column(String, nullable=True)

    # Ground truth
    is_churned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    churned_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner: Mapped["User"] = relationship("User", back_populates="customers")
    predictions: Mapped[list["ChurnPrediction"]] = relationship(
        "ChurnPrediction", back_populates="customer", cascade="all, delete-orphan"
    )