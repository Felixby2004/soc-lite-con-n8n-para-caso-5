"""Caso 5 · Monitoreo de accesos e indicadores IP."""
from datetime import datetime, timedelta
from typing import Annotated

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import distinct, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import CurrentUser, DbSession, require_ingest_key, require_permissions, utcnow
from app.core.config import settings
from app.models import AccessAnomaly, AccessIoC, AccessLog, AccessReview, Alert
from app.models.enums import AuditAction
from app.schemas.access import (
    AccessBatch, AccessImportResult, AccessIoCInput, AccessIoCItem, AccessLogItem, AccessProfile,
    AccessPreview, AccessReviewInput, AccessReviewItem, AccessSummary, Identifier, Source,
)
from app.schemas.access_evaluation import AccessEvaluation, EvaluationFormat, EvaluationScope
from app.schemas.common import Page
from app.services.access_evaluation import evaluate_accesses
from app.services.access_evaluation_report import MEDIA_TYPES, render_evaluation
from app.services.access_scoring import ALERT_THRESHOLD, BASELINE_DAYS, MINIMUM_SAMPLES, baseline_devices, baseline_hours
from app.services.access_service import (
    DEMO_SOURCE, AccessEventConflict, active_iocs, assess_event, ingest_access, load_demo, profile_history,
    validate_access_time,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/access", tags=["Monitoreo de accesos"])
AccessReader = Annotated[CurrentUser, Depends(require_permissions("access:read"))]
AccessWriter = Annotated[CurrentUser, Depends(require_permissions("access:write"))]
IoCWriter = Annotated[CurrentUser, Depends(require_permissions("access:ioc"))]
AccessReviewer = Annotated[CurrentUser, Depends(require_permissions("access:read", "access:review"))]
EvaluationExporter = Annotated[CurrentUser, Depends(require_permissions("access:read", "reports:export"))]
PageNumber = Annotated[int, Query(ge=1, le=1_000_000)]
EvaluationDays = Annotated[int, Query(ge=1, le=90)]
EvaluationThreshold = Annotated[int, Query(ge=1, le=100)]


@router.get("/summary", response_model=AccessSummary)
async def summary(db: DbSession, current: AccessReader):
    now = utcnow()
    events, accounts = (await db.execute(select(
        func.count(AccessLog.id), func.count(distinct(func.row(AccessLog.source, AccessLog.account))),
    ))).one()
    anomalies = await db.scalar(select(func.count()).select_from(AccessAnomaly))
    active_iocs = await db.scalar(select(func.count()).select_from(AccessIoC).where(
        AccessIoC.expires_at > now, AccessIoC.revoked_at.is_(None),
    ))
    return AccessSummary(
        events=events, accounts=accounts, anomalies=anomalies, active_iocs=active_iocs,
        demo_enabled=settings.DEMO_MODE,
    )


@router.get("/events", response_model=Page[AccessLogItem])
async def events(
    db: DbSession, current: AccessReader,
    source: Source | None = None, account: Identifier | None = None, anomalies_only: bool = False,
    page: PageNumber = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    filters = []
    if source:
        filters.append(AccessLog.source == source)
    if account:
        filters.append(AccessLog.account == account)
    if anomalies_only:
        filters.append(AccessAnomaly.access_log_id.is_not(None))
    total = await db.scalar(
        select(func.count()).select_from(AccessLog).outerjoin(AccessAnomaly).where(*filters)
    )
    rows = await db.execute(
        select(AccessLog, AccessAnomaly.access_log_id, Alert.id, AccessReview)
        .outerjoin(AccessAnomaly, AccessAnomaly.access_log_id == AccessLog.id)
        .outerjoin(Alert, (Alert.id == AccessAnomaly.alert_id) & Alert.deleted_at.is_(None))
        .outerjoin(AccessReview, AccessReview.access_log_id == AccessLog.id)
        .where(*filters)
        .order_by(AccessLog.occurred_at.desc(), AccessLog.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = [
        AccessLogItem(
            id=log.id, source=log.source, event_id=log.event_id, account=log.account,
            occurred_at=log.occurred_at, outcome=log.outcome,
            source_ip=str(log.source_ip) if log.source_ip is not None else None,
            device_id=log.device_id, network=log.network, score=log.score,
            signals=log.signals, baseline_size=log.baseline_size,
            is_anomaly=anomaly_id is not None, alert_id=alert_id,
            review=AccessReviewItem.model_validate(review) if review else None,
        )
        for log, anomaly_id, alert_id, review in rows
    ]
    return Page.build(items, total or 0, page, page_size)


@router.put("/events/{log_id}/review", response_model=AccessReviewItem)
async def review_access(log_id: int, body: AccessReviewInput, db: DbSession, current: AccessReviewer):
    source = await db.scalar(select(AccessLog.source).where(AccessLog.id == log_id).with_for_update())
    if source is None:
        raise HTTPException(404, "Acceso no encontrado.")
    if source == DEMO_SOURCE:
        raise HTTPException(409, "La muestra simulada tiene etiquetas de referencia fijas.")

    review = await db.get(AccessReview, log_id)
    before = AccessReviewItem.model_validate(review).model_dump(mode="json") if review else None
    if review is None:
        review = AccessReview(access_log_id=log_id)
        db.add(review)
    review.label = body.label
    review.note = body.note or None
    review.reviewed_by = current.id
    review.reviewed_at = utcnow()
    item = AccessReviewItem.model_validate(review)
    await db.commit()
    await AuditService(db).log(
        module="access", action=AuditAction.UPDATE, entity="access_review", entity_id=log_id,
        detail="Validación humana de un acceso", before=before, after=item.model_dump(mode="json"),
    )
    return item


@router.get("/evaluation", response_model=AccessEvaluation)
async def evaluation(
    db: DbSession, current: AccessReader, scope: EvaluationScope = "operation",
    days: EvaluationDays = 30, threshold: EvaluationThreshold = ALERT_THRESHOLD,
):
    now = utcnow()
    return await evaluate_accesses(db, scope, now - timedelta(days=days), now, threshold)


@router.get("/evaluation/export")
async def export_evaluation(
    db: DbSession, current: EvaluationExporter, format: EvaluationFormat = "pdf",
    scope: EvaluationScope = "operation", days: EvaluationDays = 30,
    threshold: EvaluationThreshold = ALERT_THRESHOLD,
):
    now = utcnow()
    result = await evaluate_accesses(db, scope, now - timedelta(days=days), now, threshold)
    content = await run_in_threadpool(render_evaluation, result, format)
    await AuditService(db).log(
        module="access", action=AuditAction.EXPORT, entity="access_evaluation",
        detail=f"Exportación de evaluación de accesos en {format}",
        after={"scope": scope, "days": days, "threshold": threshold, "events": result.events},
    )
    return Response(
        content=content, media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="evaluacion-accesos-{scope}.{format}"'},
    )


@router.get("/profile", response_model=AccessProfile)
async def profile(source: Source, account: Identifier, db: DbSession, current: AccessReader):
    zone = pytz.timezone(settings.TIMEZONE)
    history = await profile_history(db, source, account, utcnow())
    return AccessProfile(
        samples=len(history), devices=sorted(baseline_devices(history)), hours=sorted(baseline_hours(history, zone)),
        timezone=settings.TIMEZONE, window_days=BASELINE_DAYS, minimum_samples=MINIMUM_SAMPLES,
    )


async def import_batch(body: AccessBatch, db: DbSession, actor: str | None) -> AccessImportResult:
    if body.source == DEMO_SOURCE:
        raise HTTPException(422, "El origen demo-vpn está reservado para la demostración.")
    try:
        result = await ingest_access(db, body, utcnow())
    except AccessEventConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await log_import(db, body.source, result, actor)
    return result


async def log_import(db: DbSession, source: str, result: AccessImportResult, actor: str | None) -> None:
    await db.commit()
    await AuditService(db).log(
        module="access", action=AuditAction.CREATE, username=actor, entity="access_log",
        detail=f"Ingesta de accesos desde {source}", after=result.model_dump(),
    )


@router.post("/events/import", response_model=AccessImportResult)
async def import_events(body: AccessBatch, db: DbSession, current: AccessWriter):
    return await import_batch(body, db, current.username)


@router.post("/events/preview", response_model=AccessPreview)
async def preview_access(body: AccessBatch, db: DbSession, current: AccessWriter):
    if len(body.events) != 1:
        raise HTTPException(422, "La evaluación individual requiere exactamente un acceso.")
    if body.source == DEMO_SOURCE and not settings.DEMO_MODE:
        raise HTTPException(422, "El origen demo-vpn está reservado para la demostración.")
    now = utcnow()
    try:
        validate_access_time(body.events, now)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = await assess_event(db, body.source, body.events[0], await active_iocs(db, body, now))
    await AuditService(db).log(
        module="access", action=AuditAction.READ, entity="access_preview",
        detail="Evaluación individual de acceso", after={"score": result.score},
    )
    return result


@router.post("/events/ingest", response_model=AccessImportResult, dependencies=[Depends(require_ingest_key)])
async def ingest_events(body: AccessBatch, db: DbSession):
    return await import_batch(body, db, "system/access-ingest")


@router.post("/demo", response_model=AccessImportResult)
async def demo(db: DbSession, current: AccessWriter):
    if not settings.DEMO_MODE:
        raise HTTPException(404, "La demostración no está habilitada.")
    result = await load_demo(db, utcnow())
    await log_import(db, DEMO_SOURCE, result, current.username)
    return result


def ioc_item(indicator: AccessIoC, now: datetime) -> AccessIoCItem:
    return AccessIoCItem(
        id=indicator.id, ip_address=str(indicator.ip_address), reference=indicator.reference,
        expires_at=indicator.expires_at, active=indicator.expires_at > now and indicator.revoked_at is None,
    )


@router.get("/iocs", response_model=Page[AccessIoCItem])
async def list_iocs(db: DbSession, current: AccessReader, page: PageNumber = 1):
    now = utcnow()
    page_size = 20
    total = await db.scalar(select(func.count()).select_from(AccessIoC))
    rows = await db.scalars(
        select(AccessIoC).order_by(
            (AccessIoC.revoked_at.is_(None) & (AccessIoC.expires_at > now)).desc(), AccessIoC.id.desc(),
        ).offset((page - 1) * page_size).limit(page_size)
    )
    return Page.build([ioc_item(row, now) for row in rows], total or 0, page, page_size)


@router.put("/iocs", response_model=AccessIoCItem)
async def save_ioc(body: AccessIoCInput, db: DbSession, current: IoCWriter):
    now = utcnow()
    statement = insert(AccessIoC).values(
        ip_address=str(body.ip_address), reference=body.reference,
        expires_at=now + timedelta(days=body.ttl_days), revoked_at=None,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[AccessIoC.ip_address],
        set_={
            "reference": statement.excluded.reference, "expires_at": statement.excluded.expires_at,
            "revoked_at": None,
        },
    ).returning(AccessIoC)
    row = (await db.scalars(statement)).one()
    item = ioc_item(row, now)
    await db.commit()
    await AuditService(db).log(
        module="access", action=AuditAction.UPDATE, entity="access_ioc", entity_id=item.id,
        detail="Alta o renovación de indicador IP", after=item.model_dump(mode="json"),
    )
    return item


@router.delete("/iocs/{ioc_id}", response_model=AccessIoCItem)
async def revoke_ioc(ioc_id: int, db: DbSession, current: IoCWriter):
    now = utcnow()
    row = (await db.scalars(
        update(AccessIoC).where(AccessIoC.id == ioc_id)
        .values(revoked_at=func.coalesce(AccessIoC.revoked_at, now)).returning(AccessIoC)
    )).one_or_none()
    if row is None:
        raise HTTPException(404, "Indicador no encontrado.")
    item = ioc_item(row, now)
    await db.commit()
    await AuditService(db).log(
        module="access", action=AuditAction.UPDATE, entity="access_ioc", entity_id=item.id,
        detail="Revocación de indicador IP",
    )
    return item
