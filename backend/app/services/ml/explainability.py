"""SHAP explainability for churn predictions.

Public API:
    compute_shap(pipeline, X) -> ShapResult
    build_shap_dict(shap_row) -> dict[str, float]        for JSONB storage
    build_top_factors(shap_row, imputed_row, n) -> list   for JSONB + display
"""

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shap
from sklearn.pipeline import Pipeline

from app.services.ml.features import FEATURE_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class ShapResult:
    shap_matrix: np.ndarray  # (n_samples, n_features) — SHAP for churn class
    X_imputed: np.ndarray    # (n_samples, n_features) — post-imputer feature values


# ---------------------------------------------------------------------------
# Human-readable description templates
# {value} is the imputed feature value for the customer.
# ---------------------------------------------------------------------------
_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "recency_days": {
        "positive": "inactive for {value:.0f} days, increasing churn risk",
        "negative": "logged in {value:.0f} days ago, reducing churn risk",
    },
    "tenure_days": {
        "positive": "only {value:.0f}-day tenure, short relationship",
        "negative": "{value:.0f}-day tenure indicates loyalty",
    },
    "logins_last_30d": {
        "positive": "only {value:.0f} logins last 30 days, low engagement",
        "negative": "{value:.0f} logins last 30 days, strong engagement",
    },
    "monthly_revenue": {
        "positive": "${value:.0f}/mo revenue suggests limited buy-in",
        "negative": "${value:.0f}/mo revenue indicates deep commitment",
    },
    "feature_usage_score": {
        "positive": "product usage at {value:.0f}%, low adoption",
        "negative": "product usage at {value:.0f}%, high adoption",
    },
    "nps_score": {
        "positive": "NPS of {value:.0f} signals low satisfaction",
        "negative": "NPS of {value:.0f} signals high satisfaction",
    },
    "support_tickets_open": {
        "positive": "{value:.0f} unresolved support ticket(s), active friction",
        "negative": "only {value:.0f} open support tickets",
    },
    "support_tickets_total": {
        "positive": "{value:.0f} total support tickets, high support burden",
        "negative": "only {value:.0f} total support tickets, low friction",
    },
    "billing_issues_count": {
        "positive": "{value:.0f} billing issue(s) adding payment friction",
        "negative": "no billing issues, healthy payment history",
    },
    "support_burden": {
        "positive": "{value:.2f} tickets/month, unusually high support load",
        "negative": "low support rate of {value:.2f} tickets/month",
    },
    "open_ticket_ratio": {
        "positive": "{value:.0%} open ticket ratio, unresolved issues causing friction",
        "negative": "{value:.0%} open ticket ratio, model views as reducing churn risk",
    },
    "has_contract": {
        "positive": "no contract in place, easy to cancel",
        "negative": "under contract, reducing churn likelihood",
    },
    "contract_length_months": {
        "positive": "short or no contract ({value:.0f} months)",
        "negative": "{value:.0f}-month contract adds retention anchor",
    },
    "days_to_contract_end": {
        "positive": "contract expires/expired ({value:.0f} days), renewal risk",
        "negative": "{value:.0f} days remaining on contract, reducing churn risk",
    },
    "plan_ordinal": {
        "positive": "lower-tier plan, low switching cost",
        "negative": "higher-tier plan, greater product investment",
    },
    "company_size_ordinal": {
        "positive": "smaller company profile, higher churn likelihood",
        "negative": "larger company profile, more stable relationship",
    },
}


def _finite(v: float) -> float:
    """Replace NaN/Inf with 0.0 so JSONB can store the value safely."""
    if v != v or v == float("inf") or v == float("-inf"):
        return 0.0
    return v


def _describe(feature: str, value: float, direction: str) -> str:
    tmpl = _DESCRIPTIONS.get(feature, {}).get(direction)
    if tmpl is None:
        trend = "increasing" if direction == "positive" else "reducing"
        return f"{feature}={value:.2f}, {trend} churn risk"
    try:
        return tmpl.format(value=value)
    except (KeyError, ValueError):
        return tmpl


# ---------------------------------------------------------------------------
# Core SHAP computation
# ---------------------------------------------------------------------------
def compute_shap(pipeline: Pipeline, X: pd.DataFrame) -> ShapResult:
    """Compute SHAP values for all rows in X.

    Passes imputed data to TreeExplainer so values align with what XGBoost saw.
    Returns both the SHAP matrix and the imputed feature matrix so callers don't
    need to transform twice.
    """
    imputer = pipeline.named_steps["imputer"]
    clf = pipeline.named_steps["clf"]

    X_imputed: np.ndarray = imputer.transform(X)

    explainer = shap.TreeExplainer(clf)
    raw = explainer.shap_values(X_imputed)

    # Normalise to (n_samples, n_features) for the positive (churn) class.
    # Different SHAP versions return different shapes for binary classifiers.
    arr = np.asarray(raw)
    if arr.ndim == 3:
        # (n_classes, n_samples, n_features) — take class-1 slice
        arr = arr[1]
    elif arr.ndim == 2 and arr.shape[1] != len(FEATURE_COLUMNS):
        # Unexpected shape — log and return zeros rather than crash
        logger.warning("Unexpected SHAP shape %s; returning zeros", arr.shape)
        arr = np.zeros((len(X), len(FEATURE_COLUMNS)), dtype=float)

    logger.info("Computed SHAP values for %d customers", len(X))
    return ShapResult(shap_matrix=arr, X_imputed=X_imputed)


# ---------------------------------------------------------------------------
# Per-customer serialisers
# ---------------------------------------------------------------------------
def build_shap_dict(shap_row: np.ndarray) -> dict[str, float]:
    """Map feature names → SHAP values for one customer (full, for JSONB)."""
    return {feat: _finite(round(float(v), 6)) for feat, v in zip(FEATURE_COLUMNS, shap_row)}


def build_top_factors(
    shap_row: np.ndarray,
    imputed_row: np.ndarray,
    n: int = 5,
) -> list[dict[str, Any]]:
    """Return the top-n SHAP contributors as structured dicts.

    Each dict has: feature, shap_value, direction, feature_value, description.
    Sorted by |shap_value| descending.
    """
    triples = sorted(
        zip(FEATURE_COLUMNS, shap_row, imputed_row),
        key=lambda t: abs(t[1]),
        reverse=True,
    )[:n]

    factors = []
    for feat, shap_val, feat_val in triples:
        sv = _finite(float(shap_val))
        fv = _finite(float(feat_val))
        direction = "positive" if sv >= 0 else "negative"
        factors.append({
            "feature": feat,
            "shap_value": round(sv, 6),
            "direction": direction,
            "feature_value": round(fv, 4),
            "description": _describe(feat, fv, direction),
        })
    return factors
