"""CLI training script.

Run from the backend/ directory:

    PYTHONPATH=. python ml/train.py
    PYTHONPATH=. python ml/train.py --version v20260612-xgb-custom
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make backend/ importable when this script is run directly.
sys.path.insert(0, str(Path(__file__).parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main(version_name: str | None) -> None:
    # Import here so the logging config above takes effect first.
    from app.core.database import AsyncSessionLocal
    from app.services.ml.training import run_training

    logger.info("Starting ChurnIQ training run...")
    async with AsyncSessionLocal() as db:
        mv = await run_training(db, version_name=version_name)
        await db.commit()

    logger.info("─" * 60)
    logger.info("Version    : %s", mv.version_name)
    logger.info("Model ID   : %s", mv.id)
    logger.info("Rows       : %s", mv.training_rows)
    logger.info("AUC-ROC    : %.4f", mv.auc_roc)
    logger.info("Accuracy   : %.4f", mv.accuracy)
    logger.info("Precision  : %.4f", mv.precision_score)
    logger.info("Recall     : %.4f", mv.recall_score)
    logger.info("F1         : %.4f", mv.f1_score)
    logger.info("Artifact   : %s", mv.model_artifact_path)
    logger.info("─" * 60)
    logger.info("Top-5 features by importance:")
    importance: dict = mv.feature_importance or {}
    for i, (feat, score) in enumerate(list(importance.items())[:5], 1):
        logger.info("  %d. %-30s %.6f", i, feat, score)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train ChurnIQ XGBoost model")
    parser.add_argument(
        "--version",
        default=None,
        help="Override version name (default: v<YYYYMMDD>-xgb)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.version))
