"""Fuentes públicas verificadas; no acepta descargas de URLs arbitrarias."""
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
import json

from app.api.deps import AlertReader, CurrentUser, DbSession, require_permissions
from app.models.enums import AuditAction
from app.models import Alert
from app.services.audit_service import AuditService
from app.services.public_dataset_service import SOURCE_NAME, dataset_summary, import_dataset, load_source

router = APIRouter(prefix="/datasets", tags=["Datasets públicos"])
DatasetImporter = Annotated[CurrentUser, Depends(require_permissions("settings:write"))]
DatasetExporter = Annotated[CurrentUser, Depends(require_permissions("reports:export"))]


@router.get("/loghub-openssh/export")
async def export(db: DbSession, current: DatasetExporter):
    manifest, _ = load_source()
    rows = (await db.execute(select(Alert.raw_payload).where(
        Alert.source_name == SOURCE_NAME, Alert.deleted_at.is_(None)).order_by(Alert.id))).scalars().all()
    await AuditService(db).log(module="reports", action=AuditAction.EXPORT, user_id=current.id,
                               username=current.username, entity="public_dataset",
                               detail=f"Exportación de {len(rows)} registros reales con procedencia")
    return Response(content=json.dumps({"manifest": manifest, "records": rows}, ensure_ascii=False, indent=2),
                    media_type="application/json", headers={"Content-Disposition": 'attachment; filename="loghub-openssh-real.json"'})


@router.get("/loghub-openssh")
async def summary(db: DbSession, current: AlertReader):
    result = await dataset_summary(db)
    await AuditService(db).log(module="alerts", action=AuditAction.READ, user_id=current.id,
                               username=current.username, entity="public_dataset",
                               detail="Consulta de procedencia y estadísticas de Loghub OpenSSH")
    return result


@router.post("/loghub-openssh/import")
async def load(db: DbSession, current: DatasetImporter):
    result = await import_dataset(db)
    await AuditService(db).log(module="settings", action=AuditAction.CREATE, user_id=current.id,
                               username=current.username, entity="public_dataset",
                               detail=f"Importación Loghub: {result['imported']} nuevos, {result['skipped']} existentes",
                               after=result)
    return result
