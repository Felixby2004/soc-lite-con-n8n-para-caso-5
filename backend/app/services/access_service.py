"""Ingesta transaccional, perfiles de acceso y generación de alertas."""
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256

import pytz
from sqlalchemy import bindparam, func, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AccessAnomaly, AccessIoC, AccessLog, Alert
from app.models.enums import SeverityLevel, SourceType
from app.schemas.access import AccessBatch, AccessEvent, AccessImportResult, AccessPreview, Location
from app.services.access_scoring import (
    ALERT_THRESHOLD, BASELINE_DAYS, BASELINE_LIMIT, FAILURE_WINDOW, alert_severity, evaluate,
)

DEMO_SOURCE = "demo-vpn"


class AccessEventConflict(ValueError):
    """Un identificador de origen ya corresponde a otro contenido."""


async def profile_history(db: AsyncSession, source: str, account: str, before: datetime) -> list[AccessLog]:
    rows = await db.scalars(
        select(AccessLog)
        .where(
            AccessLog.source == source,
            AccessLog.account == account,
            AccessLog.outcome == "success",
            AccessLog.score < ALERT_THRESHOLD,
            AccessLog.occurred_at >= before - timedelta(days=BASELINE_DAYS),
            AccessLog.occurred_at < before,
        )
        .order_by(AccessLog.occurred_at.desc(), AccessLog.id.desc())
        .limit(BASELINE_LIMIT)
    )
    return list(rows)


async def lock_source(db: AsyncSession, source: str) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"soclite:access:{source}", 0))))


def validate_access_time(events: list[AccessEvent], now: datetime) -> None:
    if any(event.occurred_at > now + timedelta(minutes=5) for event in events):
        raise ValueError("Hay un acceso con fecha más de 5 minutos en el futuro.")


async def active_iocs(db: AsyncSession, batch: AccessBatch, now: datetime) -> dict[str, int]:
    ips = {str(event.source_ip) for event in batch.events if event.source_ip is not None}
    if not ips or batch.source == DEMO_SOURCE:
        return {}
    rows = await db.execute(
        select(AccessIoC.ip_address, AccessIoC.id).where(
            AccessIoC.ip_address.in_(bindparam("source_ips", list(ips), expanding=True, type_=INET())),
            AccessIoC.expires_at > now,
            AccessIoC.revoked_at.is_(None),
        )
    )
    return {str(ip): ioc_id for ip, ioc_id in rows}


async def assess_event(db: AsyncSession, source: str, event: AccessEvent, iocs: dict[str, int]) -> AccessPreview:
    history = await profile_history(db, source, event.account, event.occurred_at)
    failures = 0
    if event.outcome == "success":
        failures = await db.scalar(select(func.count()).select_from(AccessLog).where(
            AccessLog.source == source,
            AccessLog.account == event.account,
            AccessLog.outcome == "failure",
            AccessLog.occurred_at >= event.occurred_at - FAILURE_WINDOW,
            AccessLog.occurred_at < event.occurred_at,
        )) or 0
    zone = pytz.timezone(settings.TIMEZONE)
    score, signals = evaluate(event, history, zone, failures, iocs.get(str(event.source_ip)))
    return AccessPreview(score=score, signals=signals, baseline_size=len(history), severity=alert_severity(score))


async def ingest_access(db: AsyncSession, batch: AccessBatch, now: datetime) -> AccessImportResult:
    validate_access_time(batch.events, now)
    await lock_source(db, batch.source)

    existing = dict((await db.execute(
        select(AccessLog.event_id, AccessLog.fingerprint).where(
            AccessLog.source == batch.source,
            AccessLog.event_id.in_({event.event_id for event in batch.events}),
        )
    )).tuples().all())
    iocs = await active_iocs(db, batch, now)

    result = AccessImportResult()
    for event in sorted(batch.events, key=lambda item: (item.occurred_at, item.event_id)):
        fingerprint = sha256(event.model_dump_json().encode()).hexdigest()
        if event.event_id in existing:
            if existing[event.event_id] != fingerprint:
                raise AccessEventConflict(f"El evento {event.event_id} ya existe con otros datos en {batch.source}.")
            result.skipped += 1
            continue

        assessment = await assess_event(db, batch.source, event, iocs)
        ip = str(event.source_ip) if event.source_ip is not None else None
        location = event.location
        log = AccessLog(
            source=batch.source, event_id=event.event_id, account=event.account, occurred_at=event.occurred_at,
            outcome=event.outcome, source_ip=ip, device_id=event.device_id, network=event.network,
            latitude=location.latitude if location else None, longitude=location.longitude if location else None,
            accuracy_km=location.accuracy_km if location else None, fingerprint=fingerprint,
            score=assessment.score, signals=[signal.model_dump() for signal in assessment.signals],
            baseline_size=assessment.baseline_size,
        )
        db.add(log)
        await db.flush()
        if assessment.severity is not None:
            await create_alert(db, log, now, assessment.severity)
            result.anomalies += 1
        existing[event.event_id] = fingerprint
        result.imported += 1
    return result


async def create_alert(db: AsyncSession, log: AccessLog, now: datetime, severity: SeverityLevel) -> None:
    alert = Alert(
        alert_fingerprint=f"access:{log.id}",
        source_type=SourceType.API,
        source_name="Caso 5 · Demostración" if log.source == DEMO_SOURCE else "Caso 5 · Accesos",
        rule_id="ACCESS-ANOMALY",
        rule_level={SeverityLevel.MEDIUM: 8, SeverityLevel.HIGH: 12, SeverityLevel.CRITICAL: 15}[severity],
        rule_description="Anomalía de acceso detectada por perfil de comportamiento",
        rule_groups=["authentication", "behavioral_anomaly"],
        severity=severity,
        source_ip=log.source_ip,
        occurred_at=log.occurred_at,
        sla_due_at=now + timedelta(minutes=settings.SLA_MINUTES.get(severity.value, 480)),
        risk_score=log.score,
        full_log=f"Puntaje heurístico {log.score}/100. " + " ".join(signal["detail"] for signal in log.signals),
        raw_payload={"access_log_id": log.id, "heuristic_score": log.score, "signals": log.signals},
    )
    db.add(alert)
    await db.flush()
    db.add(AccessAnomaly(access_log_id=log.id, alert_id=alert.id))
    await db.flush()


async def load_demo(db: AsyncSession, now: datetime) -> AccessImportResult:
    await lock_source(db, DEMO_SOURCE)
    anchor = await db.scalar(select(AccessLog.occurred_at).where(
        AccessLog.source == DEMO_SOURCE, AccessLog.event_id == "known-1",
    ))
    if anchor is None:
        zone = pytz.timezone(settings.TIMEZONE)
        day = now.astimezone(zone).date() - timedelta(days=5)
        anchor = zone.localize(datetime.combine(day, time(8))).astimezone(timezone.utc)

    lima = {"latitude": -12.05, "longitude": -77.04, "accuracy_km": 10}
    madrid = {"latitude": 40.42, "longitude": -3.70, "accuracy_km": 10}
    scenarios = [
        (f"known-{day + 1}", anchor + timedelta(days=day), "equipo-habitual", "direct", lima)
        for day in range(4)
    ]
    last = anchor + timedelta(days=3)
    scenarios.extend([
        ("travel", last + timedelta(minutes=10), "equipo-nuevo", "direct", madrid),
        ("vpn-control", last + timedelta(minutes=20), "equipo-habitual", "vpn", madrid),
        ("night", last + timedelta(hours=14), "otro-equipo", "vpn", madrid),
    ])
    batch = AccessBatch.model_validate({
        "source": DEMO_SOURCE,
        "events": [
            {
                "event_id": event_id, "account": "cuenta.demo", "occurred_at": when, "outcome": "success",
                "device_id": device, "network": network, "source_ip": "192.0.2.10" if location == lima else "198.51.100.20",
                "location": location,
            }
            for event_id, when, device, network, location in scenarios
        ],
    })
    return await ingest_access(db, batch, now)
