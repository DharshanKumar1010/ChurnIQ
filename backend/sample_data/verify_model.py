"""Verify ModelVersion rows and load the saved artifact."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import joblib
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.prediction import ModelVersion


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ModelVersion).order_by(ModelVersion.created_at.desc())
        )
        versions = result.scalars().all()

    print(f"ModelVersion rows in DB: {len(versions)}\n")
    for mv in versions:
        print(f"  {'* ACTIVE *' if mv.is_active else '          '} {mv.version_name}")
        print(f"    id        : {mv.id}")
        print(f"    rows      : {mv.training_rows}")
        print(f"    AUC-ROC   : {mv.auc_roc}")
        print(f"    F1        : {mv.f1_score}")
        print(f"    artifact  : {mv.model_artifact_path}")
        if mv.feature_importance:
            top = list(mv.feature_importance.items())[:3]
            print(f"    top feats : {top}")
        print()

    active = next((v for v in versions if v.is_active), None)
    if active and active.model_artifact_path:
        pipeline = joblib.load(active.model_artifact_path)
        print(f"Loaded artifact: {pipeline}")
        print(f"Pipeline steps : {list(pipeline.named_steps)}")


asyncio.run(main())
