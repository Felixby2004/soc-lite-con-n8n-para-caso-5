"""Evaluación reproducible con el historial previo de cada cuenta y origen."""
from datetime import timedelta, tzinfo
from math import asin, cos, radians, sin, sqrt
from typing import Sequence

from app.models.access import AccessLog
from app.models.enums import SeverityLevel
from app.schemas.access import AccessEvent, Location, Signal

BASELINE_DAYS = 30
BASELINE_LIMIT = 100
MINIMUM_SAMPLES = 3
ALERT_THRESHOLD = 50
FAILURE_WINDOW = timedelta(minutes=15)
FAILURE_THRESHOLD = 5
MAX_ACCURACY_KM = 50


def alert_severity(score: int) -> SeverityLevel | None:
    if score >= 85:
        return SeverityLevel.CRITICAL
    if score >= 70:
        return SeverityLevel.HIGH
    if score >= ALERT_THRESHOLD:
        return SeverityLevel.MEDIUM
    return None


def baseline_hours(history: Sequence[AccessLog], timezone: tzinfo) -> set[int]:
    return {sample.occurred_at.astimezone(timezone).hour for sample in history}


def baseline_devices(history: Sequence[AccessLog]) -> set[str]:
    return {sample.device_id for sample in history if sample.device_id is not None}


def geo_signal(event: AccessEvent, history: Sequence[AccessLog]) -> Signal | None:
    location = event.location
    if event.network != "direct" or location is None or location.accuracy_km > MAX_ACCURACY_KM:
        return None

    for previous in history:
        elapsed_hours = (event.occurred_at - previous.occurred_at).total_seconds() / 3600
        if elapsed_hours > 12:
            break
        if (
            elapsed_hours <= 0
            or previous.network != "direct"
            or previous.latitude is None
            or previous.longitude is None
            or previous.accuracy_km is None
            or previous.accuracy_km > MAX_ACCURACY_KM
        ):
            continue
        origin = Location(
            latitude=previous.latitude, longitude=previous.longitude, accuracy_km=previous.accuracy_km
        )
        distance = conservative_distance_km(origin, location)
        speed = distance / elapsed_hours
        if distance >= 500 and speed >= 900:
            return Signal(
                code="geo_velocity", points=60,
                detail=f"Al menos {distance:.0f} km en {elapsed_hours * 60:.1f} min ({speed:.0f} km/h).",
            )
        break
    return None


def conservative_distance_km(origin: Location, destination: Location) -> float:
    lat1, lat2 = radians(origin.latitude), radians(destination.latitude)
    lat_delta = lat2 - lat1
    lon_delta = radians(destination.longitude - origin.longitude)
    a = sin(lat_delta / 2) ** 2 + cos(lat1) * cos(lat2) * sin(lon_delta / 2) ** 2
    distance = 6371 * 2 * asin(sqrt(min(1.0, a)))
    return max(0.0, distance - origin.accuracy_km - destination.accuracy_km)


def evaluate(
    event: AccessEvent,
    history: Sequence[AccessLog],
    timezone: tzinfo,
    recent_failures: int,
    ioc_id: int | None,
) -> tuple[int, list[Signal]]:
    signals = []
    if ioc_id is not None:
        signals.append(Signal(code="ioc_match", points=60, detail=f"Coincide con el indicador IP vigente #{ioc_id}."))

    if event.outcome == "success":
        if recent_failures >= FAILURE_THRESHOLD:
            signals.append(Signal(
                code="failure_burst", points=35,
                detail=f"Hubo {recent_failures} fallos para esta cuenta en los 15 min anteriores.",
            ))

        geography = geo_signal(event, history)
        if geography:
            signals.append(geography)

        if len(history) >= MINIMUM_SAMPLES:
            hour = event.occurred_at.astimezone(timezone).hour
            hours = baseline_hours(history, timezone)
            if hours.isdisjoint({(hour + delta) % 24 for delta in range(-2, 3)}):
                signals.append(Signal(
                    code="unusual_hour", points=20,
                    detail=f"Acceso en la franja de las {hour:02}:00 ({timezone}) fuera del patrón observado.",
                ))

            devices = baseline_devices(history)
            known_samples = sum(sample.device_id is not None for sample in history)
            if event.device_id is not None and event.device_id not in devices and known_samples >= MINIMUM_SAMPLES:
                signals.append(Signal(
                    code="new_device", points=30, detail="El dispositivo no aparece en el historial de la cuenta.",
                ))

    return min(100, sum(signal.points for signal in signals)), signals
