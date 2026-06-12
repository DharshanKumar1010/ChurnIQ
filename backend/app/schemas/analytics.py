"""Pydantic schemas for the analytics router."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class SnapshotResponse(BaseModel):
    id: uuid.UUID | None = None
    snapshot_date: date
    total_customers: int
    active_customers: int
    churned_this_period: int
    churn_rate: Decimal | None = None
    mrr: Decimal | None = None
    mrr_at_risk: Decimal | None = None
    avg_churn_probability: Decimal | None = None
    critical_risk_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SnapshotListResponse(BaseModel):
    snapshots: list[SnapshotResponse]
    total: int
