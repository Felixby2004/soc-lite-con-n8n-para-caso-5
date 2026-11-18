"""Datos y características disponibles cuando se puntúa un acceso."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from random import Random
from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessLog, AccessReview
from app.schemas.access_ml import DataScope
from app.services.access_service import DEMO_SOURCE

MAX_REVIEWED_EVENTS = 20_000
OUTER_FOLDS = 5
INNER_FOLDS = 3
FEATURES = {
    "failed": "Acceso fallido",
    "has_ip": "IP disponible",
    "has_device": "Dispositivo disponible",
    "direct": "Conexión directa",
    "vpn_or_proxy": "Conexión VPN o proxy",
    "history": "Tamaño del historial",
    "geo_velocity": "Velocidad geográfica",
    "unusual_hour": "Horario atípico",
    "new_device": "Dispositivo nuevo",
    "failure_burst": "Fallos previos",
    "ioc_match": "Indicador IP vigente",
}
DEMO_VERSION = "auth-features-v1"


@dataclass(frozen=True)
class TrainingRow:
    timestamp: datetime
    label: int
    features: tuple[float, ...]
    heuristic_score: int


def feature_vector(
    outcome: str, ip: bool, device: bool, network: str, baseline_size: int, signal_codes: Iterable[str],
) -> tuple[float, ...]:
    codes = set(signal_codes)
    return (
        float(outcome == "failure"), float(ip), float(device), float(network == "direct"),
        float(network in ("vpn", "proxy")), baseline_size / 100,
        *(float(code in codes) for code in ("geo_velocity", "unusual_hour", "new_device", "failure_burst", "ioc_match")),
    )


def simulated_rows() -> list[TrainingRow]:
    rng = Random(7321)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for day in range(100):
        anomalies = set(rng.sample(range(12), 3))
        for index in range(12):
            # La etiqueta representa el escenario elegido antes de generar sus señales.
            label = int(index in anomalies)
            failed = rng.random() < (0.36 if label else 0.18)
            ip = rng.random() < 0.92
            device = rng.random() < 0.83
            network = rng.choices(("direct", "vpn", "proxy", "unknown"), (68, 22, 3, 7))[0]
            history = rng.randrange(0, 75)
            codes = []
            score = 0
            rules = (
                ("geo_velocity", 60, not failed and network == "direct" and history > 0, 0.035, 0.38),
                ("unusual_hour", 20, not failed and history >= 3, 0.19, 0.55),
                ("new_device", 30, not failed and device and history >= 3, 0.16, 0.66),
                ("failure_burst", 35, not failed, 0.07, 0.42),
                ("ioc_match", 60, ip, 0.018, 0.40),
            )
            for code, points, eligible, expected_rate, anomalous_rate in rules:
                if eligible and rng.random() < (anomalous_rate if label else expected_rate):
                    codes.append(code)
                    score += points
            features = feature_vector("failure" if failed else "success", ip, device, network, history, codes)
            rows.append(TrainingRow(start + timedelta(days=day, hours=2 * index), label, features, min(100, score)))
    return rows


async def load_training_data(
    db: AsyncSession, scope: DataScope, days: int, now: datetime,
) -> tuple[list[TrainingRow], int]:
    if scope == "demo":
        rows = simulated_rows()
        return rows, len(rows)

    filters = (AccessLog.source != DEMO_SOURCE, AccessLog.occurred_at.between(now - timedelta(days=days), now))
    total = await db.scalar(select(func.count()).select_from(AccessLog).where(*filters))
    reviewed = await db.execute(
        select(
            AccessLog.occurred_at, AccessReview.label, AccessLog.outcome, AccessLog.source_ip.is_not(None),
            AccessLog.device_id.is_not(None), AccessLog.network, AccessLog.baseline_size, AccessLog.signals, AccessLog.score,
        )
        .select_from(AccessLog)
        .join(AccessReview, AccessReview.access_log_id == AccessLog.id)
        .where(*filters)
        .order_by(AccessLog.occurred_at, AccessLog.id)
        .limit(MAX_REVIEWED_EVENTS + 1)
    )
    rows = [
        TrainingRow(ts, int(label == "anomalous"),
                    feature_vector(outcome, ip, device, network, size, (signal["code"] for signal in signals)), score)
        for ts, label, outcome, ip, device, network, size, signals, score in reviewed
    ]
    if len(rows) > MAX_REVIEWED_EVENTS:
        raise ValueError(f"El período supera {MAX_REVIEWED_EVENTS} eventos revisados. Reduce la ventana.")
    return rows, total or 0


def dataset_fingerprint(rows: Sequence[TrainingRow]) -> str:
    payload = [(row.timestamp.astimezone(timezone.utc).isoformat(), row.label, row.features, row.heuristic_score)
               for row in rows]
    return sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def describe(rows: Sequence[TrainingRow]) -> dict:
    anomalous = sum(row.label for row in rows)
    return {
        "events": len(rows), "anomalous": anomalous, "expected": len(rows) - anomalous,
        "days": len({utc_day(row) for row in rows}),
        "from_at": rows[0].timestamp.isoformat() if rows else None,
        "to_at": rows[-1].timestamp.isoformat() if rows else None,
    }


def utc_day(row: TrainingRow) -> str:
    return row.timestamp.astimezone(timezone.utc).date().isoformat()


def chronological_split(rows: Sequence[TrainingRow]) -> tuple[list[TrainingRow], list[TrainingRow], list[TrainingRow]]:
    day_order = sorted({utc_day(row) for row in rows})
    development_days = len(day_order) * 70 // 100
    if development_days < OUTER_FOLDS + INNER_FOLDS + 1:
        raise ValueError("Se necesitan eventos revisados de al menos 13 días UTC para la partición y los pliegues temporales.")
    first_cut = day_order[development_days]
    second_cut = day_order[len(day_order) * 85 // 100]
    development, validation, test = [], [], []
    for row in rows:
        day = utc_day(row)
        if day < first_cut:
            development.append(row)
        elif day < second_cut:
            validation.append(row)
        else:
            test.append(row)
    return development, validation, test
