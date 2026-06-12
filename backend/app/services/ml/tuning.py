"""Optuna hyperparameter tuning for the XGBoost churn pipeline.

Public API:
    tune_hyperparameters(X, y, n_trials, scale_pos_weight) -> TuneResult

The tuner uses 5-fold stratified CV on AUC-ROC so every trial sees the full
dataset without leaking a held-out test split.  Optuna's TPE sampler explores
the space efficiently; pruning kills clearly bad trials early via
MedianPruner.

Usage (from train_tuned.py CLI script):
    result = tune_hyperparameters(X, y, n_trials=25, scale_pos_weight=spw)
    # result.best_params is ready to pass straight into XGBClassifier
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import optuna
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from app.services.ml.features import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

# Suppress Optuna's per-trial INFO chatter; we log our own summary.
optuna.logging.set_verbosity(optuna.logging.WARNING)

N_CV_FOLDS = 5
RANDOM_STATE = 42


@dataclass
class TuneResult:
    best_params: dict[str, Any]
    best_cv_auc: float
    n_trials: int
    trial_history: list[dict[str, Any]] = field(default_factory=list)


def _build_cv_pipeline(params: dict[str, Any], scale_pos_weight: float) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", XGBClassifier(
            **params,
            scale_pos_weight=scale_pos_weight,
            eval_metric="logloss",
            random_state=RANDOM_STATE,
            verbosity=0,
        )),
    ])


def tune_hyperparameters(
    X: pd.DataFrame,
    y: np.ndarray,
    n_trials: int = 25,
    scale_pos_weight: float = 1.0,
) -> TuneResult:
    """Run Optuna TPE search, return best hyperparameters and CV AUC.

    Args:
        X: Feature DataFrame (raw, with NaN — imputer is inside the pipeline).
        y: Binary target array (1 = churned).
        n_trials: Number of Optuna trials.
        scale_pos_weight: n_neg / n_pos from the training set.
    """
    cv = StratifiedKFold(n_splits=N_CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    trial_history: list[dict[str, Any]] = []

    def objective(trial: optuna.Trial) -> float:
        params: dict[str, Any] = {
            "n_estimators": trial.suggest_int("n_estimators", 80, 400),
            "max_depth": trial.suggest_int("max_depth", 3, 7),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "gamma": trial.suggest_float("gamma", 0.0, 1.0),
        }
        pipeline = _build_cv_pipeline(params, scale_pos_weight)
        scores = cross_val_score(
            pipeline, X, y,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
        )
        mean_auc = float(scores.mean())
        trial_history.append({
            "trial": trial.number,
            "cv_auc": round(mean_auc, 5),
            **{k: round(v, 5) if isinstance(v, float) else v for k, v in params.items()},
        })
        return mean_auc

    logger.info(
        "Starting Optuna tuning: %d trials, %d-fold CV, scale_pos_weight=%.2f",
        n_trials, N_CV_FOLDS, scale_pos_weight,
    )
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=0),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_trial
    logger.info(
        "Tuning complete — best CV AUC=%.5f  trial #%d",
        best.value, best.number,
    )
    logger.info("Best params: %s", best.params)

    return TuneResult(
        best_params=dict(best.params),
        best_cv_auc=float(best.value),
        n_trials=n_trials,
        trial_history=trial_history,
    )
