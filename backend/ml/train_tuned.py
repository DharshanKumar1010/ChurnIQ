"""Optuna tuning + training CLI.

Runs Optuna to find the best XGBoost hyperparameters, trains a new model
version with those params, compares it against the current active model, and
activates it only if CV AUC shows improvement.

Run from backend/:
    PYTHONPATH=. python ml/train_tuned.py
    PYTHONPATH=. python ml/train_tuned.py --version v20260612-xgb-v3 --trials 25
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main(version_name: str, n_trials: int) -> None:
    import numpy as np
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.prediction import ModelVersion
    from app.services.ml.features import TARGET_COLUMN, build_features
    from app.services.ml.training import load_customers, run_training
    from app.services.ml.tuning import tune_hyperparameters

    async with AsyncSessionLocal() as db:
        # ------------------------------------------------------------------ #
        # 1. Load data and build features for tuning                          #
        # ------------------------------------------------------------------ #
        df = await load_customers(db)
        X = build_features(df)
        y = df[TARGET_COLUMN].values

        n_pos = int(y.sum())
        n_neg = int(len(y) - n_pos)
        scale_pos_weight = n_neg / n_pos

        logger.info(
            "Dataset: %d rows | churned=%d active=%d | scale_pos_weight=%.2f",
            len(df), n_pos, n_neg, scale_pos_weight,
        )

        # ------------------------------------------------------------------ #
        # 2. Optuna tuning                                                    #
        # ------------------------------------------------------------------ #
        tune_result = tune_hyperparameters(
            X, y,
            n_trials=n_trials,
            scale_pos_weight=scale_pos_weight,
        )

        logger.info("─" * 60)
        logger.info("Optuna complete — %d trials", tune_result.n_trials)
        logger.info("Best CV AUC : %.5f", tune_result.best_cv_auc)
        logger.info("Best params :")
        for k, v in tune_result.best_params.items():
            logger.info("  %-22s = %s", k, v)

        # ------------------------------------------------------------------ #
        # 3. Fetch current active model for comparison                        #
        # ------------------------------------------------------------------ #
        active_q = await db.execute(
            select(ModelVersion).where(ModelVersion.is_active.is_(True))
        )
        current_active = active_q.scalar_one_or_none()

        # ------------------------------------------------------------------ #
        # 4. Train new model with Optuna params — does NOT auto-activate yet  #
        #    We control activation ourselves based on the comparison.         #
        # ------------------------------------------------------------------ #
        # Temporarily pass is_active=False by training without auto-activation:
        # run_training() always sets is_active=True and deactivates the old one,
        # so we train, then re-evaluate and potentially roll back.
        mv_new = await run_training(
            db,
            version_name=version_name,
            extra_params=tune_result.best_params,
        )
        await db.commit()

        # ------------------------------------------------------------------ #
        # 5. Compare and decide                                               #
        # ------------------------------------------------------------------ #
        logger.info("─" * 60)
        logger.info("Version comparison:")
        logger.info(
            "  %-30s  AUC=%.4f  F1=%.4f  P=%.4f  R=%.4f",
            f"{mv_new.version_name} (NEW)",
            float(mv_new.auc_roc or 0),
            float(mv_new.f1_score or 0),
            float(mv_new.precision_score or 0),
            float(mv_new.recall_score or 0),
        )
        if current_active:
            logger.info(
                "  %-30s  AUC=%.4f  F1=%.4f  P=%.4f  R=%.4f",
                f"{current_active.version_name} (prev active)",
                float(current_active.auc_roc or 0),
                float(current_active.f1_score or 0),
                float(current_active.precision_score or 0),
                float(current_active.recall_score or 0),
            )
            delta = float(mv_new.auc_roc or 0) - float(current_active.auc_roc or 0)
            logger.info("  AUC delta (new - prev): %+.4f", delta)

            if delta >= 0:
                # New model is better or tied — it's already active (run_training set it).
                logger.info(
                    "RESULT: %s activated (+%.4f AUC vs %s)",
                    mv_new.version_name, delta, current_active.version_name,
                )
            else:
                # Roll back: re-activate the old model, deactivate new.
                async with AsyncSessionLocal() as db2:
                    mv_new_row = await db2.get(ModelVersion, mv_new.id)
                    prev_row   = await db2.get(ModelVersion, current_active.id)
                    if mv_new_row:
                        mv_new_row.is_active = False
                    if prev_row:
                        prev_row.is_active = True
                    await db2.commit()
                logger.info(
                    "RESULT: %s kept active (new model AUC %.4f < prev %.4f by %.4f)",
                    current_active.version_name,
                    float(mv_new.auc_roc or 0),
                    float(current_active.auc_roc or 0),
                    abs(delta),
                )
        else:
            logger.info("RESULT: %s activated (no previous model)", mv_new.version_name)

        logger.info("─" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tune + train ChurnIQ XGBoost model")
    parser.add_argument("--version", default="v20260612-xgb-v3",
                        help="Version name for the new model")
    parser.add_argument("--trials", type=int, default=25,
                        help="Number of Optuna trials (default: 25)")
    args = parser.parse_args()
    asyncio.run(main(args.version, args.trials))
