import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.customer import PlanType


class CustomerBase(BaseModel):
    external_id: str | None = None
    name: str
    email: str | None = None
    phone: str | None = None

    plan: PlanType = PlanType.starter
    monthly_revenue: Decimal = Decimal("0.00")
    contract_length_months: int | None = None
    signup_date: date
    contract_end_date: date | None = None

    last_activity_date: date | None = None
    logins_last_30d: int = 0
    feature_usage_score: Decimal | None = None
    support_tickets_open: int = 0
    support_tickets_total: int = 0
    nps_score: int | None = None
    billing_issues_count: int = 0

    country: str | None = None
    industry: str | None = None
    company_size: str | None = None

    is_churned: bool = False
    churned_at: date | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()

    @field_validator("country")
    @classmethod
    def country_iso2(cls, v: str | None) -> str | None:
        if v is not None and len(v) != 2:
            raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code")
        return v.upper() if v else v

    @field_validator("nps_score")
    @classmethod
    def nps_range(cls, v: int | None) -> int | None:
        if v is not None and not (-100 <= v <= 100):
            raise ValueError("nps_score must be between -100 and 100")
        return v

    @field_validator("monthly_revenue")
    @classmethod
    def revenue_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("monthly_revenue must be non-negative")
        return v


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    """All fields optional — only supplied fields are written to the DB."""

    external_id: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None

    plan: PlanType | None = None
    monthly_revenue: Decimal | None = None
    contract_length_months: int | None = None
    signup_date: date | None = None
    contract_end_date: date | None = None

    last_activity_date: date | None = None
    logins_last_30d: int | None = None
    feature_usage_score: Decimal | None = None
    support_tickets_open: int | None = None
    support_tickets_total: int | None = None
    nps_score: int | None = None
    billing_issues_count: int | None = None

    country: str | None = None
    industry: str | None = None
    company_size: str | None = None

    is_churned: bool | None = None
    churned_at: date | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("name must not be blank")
        return v.strip() if v else v

    @field_validator("country")
    @classmethod
    def country_iso2(cls, v: str | None) -> str | None:
        if v is not None and len(v) != 2:
            raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code")
        return v.upper() if v else v

    @field_validator("nps_score")
    @classmethod
    def nps_range(cls, v: int | None) -> int | None:
        if v is not None and not (-100 <= v <= 100):
            raise ValueError("nps_score must be between -100 and 100")
        return v

    @field_validator("monthly_revenue")
    @classmethod
    def revenue_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("monthly_revenue must be non-negative")
        return v


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    latest_risk_tier: str | None = None
    latest_churn_probability: Decimal | None = None


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    skip: int
    limit: int
