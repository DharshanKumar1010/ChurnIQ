"""XGBoost churn prediction training pipeline.

Entry point: run_training(db) — async, loads customers, trains, saves artifact,
writes a ModelVersion record, and marks it active.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from xgboost import XGBClassifier

from app.models.customer import Customer
from app.models.prediction import ModelVersion
from app.services.ml.features import FEATURE_COLUMNS, TARGET_COLUMN, build_features

logger = logging.getLogger(__name__)

# Artifact root: backend/models/<version_name>/pipeline.joblib
_ARTIFACT_ROOT = Path(__file__).parents[4] / "models"

MIN_TRAINING_ROWS = 20
TEST_SIZE = 0.2
RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class TrainingResult:
    version_name: str
    artifact_path: Path
    feature_names: list[str]
    feature_importance: dict[str, float]
    hyperparameters: dict[str, Any]
    n_training_rows: int
    n_test_rows: int
    auc_roc: float
    accuracy: float
    precision: float
    recall: float
    f1: float


# ---------------------------------------------------------------------------
# DB → DataFrame
# ---------------------------------------------------------------------------
async def load_customers(db: AsyncSession) -> pd.DataFrame:
    """Load every Customer row into a flat DataFrame."""
    result = await db.execute(select(Customer))
    customers = result.scalars().all()

    if not customers:
        raise ValueError(
            "No customers in the database. "
            "Run the bulk-import endpoint with sample_data/customers_sample.csv first."
        )

    rows = [
        {
            "id": str(c.id),
            "signup_date": c.signup_date,
            "last_activity_date": c.last_activity_date,
            "logins_last_30d": c.logins_last_30d,
            "monthly_revenue": float(c.monthly_revenue),
            "support_tickets_open": c.support_tickets_open,
            "support_tickets_total": c.support_tickets_total,
            "billing_issues_count": c.billing_issues_count,
            "nps_score": c.nps_score,
            "feature_usage_score": float(c.feature_usage_score) if c.feature_usage_score is not None else None,
            "contract_length_months": c.contract_length_months,
            "contract_end_date": c.contract_end_date,
            "plan": c.plan.value,
            "company_size": c.company_size,
            TARGET_COLUMN: int(c.is_churned),
        }
        for c in customers
    ]

    df = pd.DataFrame(rows)
    logger.info("Loaded %d customers from DB (churned=%d)", len(df), df[TARGET_COLUMN].sum())
    return df


# ---------------------------------------------------------------------------
# Training (sync — CPU-bound)
# ---------------------------------------------------------------------------
def _make_version_name() -> str:
    return f"v{date.today().strftime('%Y%m%d')}-xgb"


def _clean_for_json(obj: Any) -> Any:
    """Recursively replace float NaN/Inf with None so JSONB accepts the value."""
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


def _build_pipeline(
    scale_pos_weight: float,
    extra_params: dict[str, Any] | None = None,
) -> Pipeline:
    xgb_params: dict[str, Any] = {
        "n_estimators": 150,
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": round(scale_pos_weight, 4),
        "eval_metric": "logloss",
        "random_state": RANDOM_STATE,
    }
    if extra_params:
        xgb_params.update(extra_params)
        xgb_params["scale_pos_weight"] = round(scale_pos_weight, 4)
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", XGBClassifier(**xgb_params)),
    ])


def train_churn_model(
    df: pd.DataFrame,
    version_name: str,
    artifact_dir: Path,
    reference_date: date | None = None,
    extra_params: dict[str, Any] | None = None,
) -> TrainingResult:
    """Build features, train/test split, fit XGBoost, evaluate, save artifact."""
    if len(df) < MIN_TRAINING_ROWS:
        raise ValueError(
            f"Need at least {MIN_TRAINING_ROWS} customers to train; got {len(df)}."
        )

    X = build_features(df, reference_date=reference_date)
    y = df[TARGET_COLUMN].values

    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    if n_pos == 0:
        raise ValueError("No churned customers in the dataset — cannot train a classifier.")
    if n_neg == 0:
        raise ValueError("All customers are churned — cannot train a classifier.")

    logger.info(
        "Class distribution — churned: %d  active: %d  (%.1f%% churn rate)",
        n_pos, n_neg, 100 * n_pos / len(y),
    )
    if len(df) < 100:
        logger.warning(
            "Only %d training rows — model accuracy will be limited. "
            "Import more real customer data for production use.",
            len(df),
        )

    # Stratified split preserves churn ratio in both sets.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        stratify=y,
        random_state=RANDOM_STATE,
    )

    scale_pos_weight = n_neg / n_pos
    pipeline = _build_pipeline(scale_pos_weight, extra_params=extra_params)
    pipeline.fit(X_train, y_train)
    logger.info("Model fitted on %d rows", len(X_train))

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------
    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]

    metrics = {
        "auc_roc": float(roc_auc_score(y_test, y_proba)),
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
    }
    logger.info(
        "Eval — AUC=%.4f  Acc=%.4f  P=%.4f  R=%.4f  F1=%.4f",
        metrics["auc_roc"], metrics["accuracy"],
        metrics["precision"], metrics["recall"], metrics["f1"],
    )

    # ------------------------------------------------------------------
    # Feature importance (gain-based from XGBoost)
    # ------------------------------------------------------------------
    importances: np.ndarray = pipeline.named_steps["clf"].feature_importances_
    feature_importance = {
        col: round(float(imp), 6)
        for col, imp in sorted(
            zip(FEATURE_COLUMNS, importances),
            key=lambda t: t[1],
            reverse=True,
        )
    }

    # ------------------------------------------------------------------
    # Save artifact
    # ------------------------------------------------------------------
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "pipeline.joblib"
    joblib.dump(pipeline, artifact_path)

    metadata = {
        "version_name": version_name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_columns": FEATURE_COLUMNS,
        "metrics": metrics,
        "feature_importance": feature_importance,
        "hyperparameters": pipeline.named_steps["clf"].get_params(),
    }
    (artifact_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    logger.info("Artifact saved → %s", artifact_path)

    raw_params = pipeline.named_steps["clf"].get_params()
    clean_params: dict[str, Any] = _clean_for_json(
        {k: v for k, v in raw_params.items() if v is not None}
    )

    return TrainingResult(
        version_name=version_name,
        artifact_path=artifact_path,
        feature_names=FEATURE_COLUMNS,
        feature_importance=feature_importance,
        hyperparameters=clean_params,
        n_training_rows=len(X_train),
        n_test_rows=len(X_test),
        **metrics,
    )


# ---------------------------------------------------------------------------
# Async entry point
# ---------------------------------------------------------------------------
async def run_training(
    db: AsyncSession,
    version_name: str | None = None,
    reference_date: date | None = None,
    extra_params: dict[str, Any] | None = None,
) -> ModelVersion:
    """Load customers, train XGBoost, persist ModelVersion, return ORM object.

    Marks the new version active and deactivates any previous active model.
    Pass extra_params to override default XGBoost hyperparameters (e.g. from Optuna).
    """
    df = await load_customers(db)

    if version_name is None:
        version_name = _make_version_name()
        # Disambiguate if the same name already exists today.
        existing = await db.execute(
            select(ModelVersion).where(ModelVersion.version_name == version_name)
        )
        if existing.scalar_one_or_none() is not None:
            version_name = f"{version_name}-{int(datetime.now(timezone.utc).timestamp())}"

    artifact_dir = _ARTIFACT_ROOT / version_name
    result = train_churn_model(df, version_name, artifact_dir, reference_date, extra_params)

    # Deactivate the current active model (partial unique index allows only one).
    active_q = await db.execute(
        select(ModelVersion).where(ModelVersion.is_active.is_(True))
    )
    for stale in active_q.scalars().all():
        stale.is_active = False
    await db.flush()

    mv = ModelVersion(
        version_name=result.version_name,
        algorithm="xgboost",
        training_rows=result.n_training_rows + result.n_test_rows,
        auc_roc=round(result.auc_roc, 4),
        accuracy=round(result.accuracy, 4),
        precision_score=round(result.precision, 4),
        recall_score=round(result.recall, 4),
        f1_score=round(result.f1, 4),
        feature_names=result.feature_names,
        feature_importance=result.feature_importance,
        hyperparameters=result.hyperparameters,
        model_artifact_path=str(result.artifact_path),
        is_active=True,
    )
    db.add(mv)
    await db.flush()
    await db.refresh(mv)

    logger.info(
        "ModelVersion '%s' created (id=%s) and set active.",
        mv.version_name, mv.id,
    )
    return mv
