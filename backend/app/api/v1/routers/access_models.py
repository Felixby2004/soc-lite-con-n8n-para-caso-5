"""Entrenamiento y evaluación experimental de accesos."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, require_permissions, utcnow
from app.core.config import settings
from app.models import AccessModelRun
from app.models.enums import AuditAction
from app.schemas.access import AccessBatch
from app.schemas.access_evaluation import EvaluationFormat
from app.schemas.access_ml import DataScope, ModelConfiguration, ModelRunDetail, ModelRunSummary
from app.services.access_evaluation_report import MEDIA_TYPES
from app.services.access_ml_data import (
    DEMO_VERSION, FEATURES, OUTER_FOLDS, chronological_split, describe, feature_vector, load_training_data,
)
from app.services.access_ml_predict import explain_prediction
from app.services.access_ml_report import render_model_report
from app.services.access_service import active_iocs, assess_event, validate_access_time
from app.services.audit_service import AuditService

router = APIRouter(prefix="/access/models", tags=["Modelos de acceso"])
ModelReader = Annotated[CurrentUser, Depends(require_permissions("access:read"))]
ModelTrainer = Annotated[CurrentUser, Depends(require_permissions("access:read", "access:train"))]
ModelExporter = Annotated[CurrentUser, Depends(require_permissions("access:read", "reports:export"))]
ModelPredictor = Annotated[CurrentUser, Depends(require_permissions("access:read", "access:write"))]


def require_scope(scope: DataScope) -> None:
    if scope == "demo" and not settings.DEMO_MODE:
        raise HTTPException(404, "La fuente simulada no está habilitada.")


async def get_run(db: DbSession, run_id: int, *, completed=False) -> AccessModelRun:
    run = await db.get(AccessModelRun, run_id)
    if run is None:
        raise HTTPException(404, "Ejecución no encontrada.")
    if completed and run.status != "completed":
        raise HTTPException(409, "La ejecución todavía no tiene un modelo entrenado.")
    return run


@router.get("/dataset")
async def dataset(
    db: DbSession, current: ModelReader, scope: DataScope = "operation",
    days: Annotated[int, Query(ge=14, le=365)] = 90,
):
    require_scope(scope)
    try:
        rows, total = await load_training_data(db, scope, days, utcnow())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    partitions = None
    reason = None
    try:
        parts = chronological_split(rows)
        partitions = dict(zip(("development", "validation", "test"), (describe(part) for part in parts), strict=True))
        if any({row.label for row in part} != {0, 1} for part in parts):
            reason = "Cada partición necesita eventos esperados y anómalos."
    except ValueError as error:
        reason = str(error)
    return {
        **describe(rows), "total_events": total, "scope": scope,
        "demo_version": DEMO_VERSION if scope == "demo" else None, "partitions": partitions, "reason": reason,
        "features": [{"label": label, "present": sum(row.features[i] > 0 for row in rows)}
                     for i, label in enumerate(FEATURES.values())],
    }


@router.get("/runs", response_model=list[ModelRunSummary])
async def runs(db: DbSession, current: ModelReader):
    return list(await db.scalars(select(AccessModelRun).order_by(AccessModelRun.id.desc()).limit(40)))


@router.post("/runs", status_code=202, response_model=ModelRunDetail)
async def enqueue(body: ModelConfiguration, db: DbSession, current: ModelTrainer):
    require_scope(body.scope)
    run = AccessModelRun(
        requested_by=current.id, status="queued", configuration=body.model_dump(),
        progress={"completed": 0, "total": (OUTER_FOLDS + 1) * body.trials, "trials": []},
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "Ya hay una ejecución en cola o en curso.") from error
    await AuditService(db).log(
        module="access", action=AuditAction.CREATE, entity="access_model_run", entity_id=run.id,
        detail="Entrenamiento de accesos encolado", after=body.model_dump(),
    )
    return run


@router.get("/runs/{run_id}", response_model=ModelRunDetail)
async def run_detail(run_id: int, db: DbSession, current: ModelReader):
    return await get_run(db, run_id)


@router.get("/runs/{run_id}/export")
async def export_model(run_id: int, db: DbSession, current: ModelExporter, format: EvaluationFormat = "pdf"):
    run = await get_run(db, run_id, completed=True)
    content = await run_in_threadpool(render_model_report, run.id, run.configuration, run.result, format)
    await AuditService(db).log(
        module="access", action=AuditAction.EXPORT, entity="access_model_run", entity_id=run_id,
        detail=f"Exportación del entrenamiento en {format}",
    )
    return Response(
        content=content, media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="modelo-accesos-{run_id}.{format}"'},
    )


@router.post("/runs/{run_id}/predict")
async def predict(run_id: int, body: AccessBatch, db: DbSession, current: ModelPredictor):
    run = await get_run(db, run_id, completed=True)
    if len(body.events) != 1:
        raise HTTPException(422, "La inferencia individual requiere exactamente un acceso.")
    event = body.events[0]
    now = utcnow()
    try:
        validate_access_time(body.events, now)
        preview = await assess_event(db, body.source, event, await active_iocs(db, body, now))
        features = feature_vector(
            event.outcome, event.source_ip is not None, event.device_id is not None,
            event.network, preview.baseline_size, (signal.code for signal in preview.signals),
        )
        prediction = explain_prediction(run.artifact, features, run.result["model"]["threshold"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    await AuditService(db).log(
        module="access", action=AuditAction.READ, entity="access_model_prediction", entity_id=run_id,
        detail="Predicción individual de acceso",
    )
    return {"run_id": run_id, "scope": run.configuration["scope"], "heuristic": preview, **prediction}
