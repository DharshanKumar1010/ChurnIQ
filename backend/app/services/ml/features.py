"""Feature engineering for churn prediction.

Raw Customer columns → numeric feature matrix consumed by the XGBoost pipeline.
All transforms are deterministic given a reference_date; no I/O here.
"""

from datetime import date

import numpy as np
import pandas as pd

# Ordered list used to guarantee column order into the model.
FEATURE_COLUMNS: list[str] = [
    # RFM-style
    "tenure_days",
    "recency_days",
    "logins_last_30d",
    "monthly_revenue",
    # Support / friction
    "support_tickets_open",
    "support_tickets_total",
    "billing_issues_count",
    "support_burden",          # tickets_total / tenure_months
    "open_ticket_ratio",       # open / (total + 1)
    # Engagement
    "feature_usage_score",     # 0-100, NaN → imputed
    "nps_score",               # -100 to 100, NaN → imputed
    # Contract
    "contract_length_months",  # 0 = month-to-month
    "has_contract",            # binary
    "days_to_contract_end",    # NaN for no contract
    # Categorical (ordinal encoded)
    "plan_ordinal",
    "company_size_ordinal",
]

TARGET_COLUMN: str = "is_churned"

_PLAN_ORDINAL: dict[str, int] = {
    "free": 0,
    "starter": 1,
    "growth": 2,
    "enterprise": 3,
}
_SIZE_ORDINAL: dict[str, int] = {
    "small": 0,
    "mid": 1,
    "large": 2,
}


def build_features(
    df: pd.DataFrame,
    reference_date: date | None = None,
) -> pd.DataFrame:
    """Return a DataFrame with exactly FEATURE_COLUMNS from raw customer rows.

    NaN values remain for columns that have natural missingness
    (feature_usage_score, nps_score, days_to_contract_end); the sklearn
    SimpleImputer in the training pipeline handles them.

    Args:
        df: Raw customer DataFrame produced by load_customers().
        reference_date: Anchor date for recency/tenure calculations.
                        Defaults to today.
    """
    if reference_date is None:
        reference_date = date.today()

    ref = pd.Timestamp(reference_date)
    out = pd.DataFrame(index=df.index)

    # ------------------------------------------------------------------
    # Tenure & recency
    # ------------------------------------------------------------------
    signup_ts = pd.to_datetime(df["signup_date"])
    out["tenure_days"] = (ref - signup_ts).dt.days.clip(lower=0)

    activity_ts = pd.to_datetime(df["last_activity_date"])
    # Fall back to signup_date when last_activity_date is missing.
    activity_ts = activity_ts.fillna(signup_ts)
    out["recency_days"] = (ref - activity_ts).dt.days.clip(lower=0)

    # ------------------------------------------------------------------
    # Frequency & monetary
    # ------------------------------------------------------------------
    out["logins_last_30d"] = df["logins_last_30d"].fillna(0).astype(float)
    out["monthly_revenue"] = df["monthly_revenue"].astype(float)

    # ------------------------------------------------------------------
    # Support burden
    # ------------------------------------------------------------------
    out["support_tickets_open"] = df["support_tickets_open"].fillna(0).astype(float)
    out["support_tickets_total"] = df["support_tickets_total"].fillna(0).astype(float)
    out["billing_issues_count"] = df["billing_issues_count"].fillna(0).astype(float)

    tenure_months = (out["tenure_days"] / 30.0).clip(lower=1)
    out["support_burden"] = out["support_tickets_total"] / tenure_months
    out["open_ticket_ratio"] = out["support_tickets_open"] / (
        out["support_tickets_total"] + 1
    )

    # ------------------------------------------------------------------
    # Engagement (NaN preserved for imputer)
    # ------------------------------------------------------------------
    out["feature_usage_score"] = pd.to_numeric(df["feature_usage_score"], errors="coerce")
    out["nps_score"] = pd.to_numeric(df["nps_score"], errors="coerce")

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------
    out["contract_length_months"] = df["contract_length_months"].fillna(0).astype(float)
    out["has_contract"] = (~df["contract_end_date"].isna()).astype(float)

    contract_end_ts = pd.to_datetime(df["contract_end_date"])
    out["days_to_contract_end"] = (contract_end_ts - ref).dt.days  # NaN if no contract

    # ------------------------------------------------------------------
    # Categorical → ordinal
    # ------------------------------------------------------------------
    out["plan_ordinal"] = (
        df["plan"].str.lower().map(_PLAN_ORDINAL).fillna(1).astype(float)
    )
    out["company_size_ordinal"] = (
        df["company_size"].str.lower().map(_SIZE_ORDINAL).fillna(-1).astype(float)
    )

    return out[FEATURE_COLUMNS]
