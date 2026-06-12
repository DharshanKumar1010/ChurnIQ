import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "snapshot_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_customers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_customers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    churned_this_period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    churn_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    mrr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    mrr_at_risk: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    avg_churn_probability: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    critical_risk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_risk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_risk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_risk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="analytics_snapshots")