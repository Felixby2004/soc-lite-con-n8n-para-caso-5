from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.access import AccessLog
from app.schemas.access import AccessEvent, AccessIoCInput
from app.services.access_scoring import evaluate

NOW = datetime(2026, 10, 9, 13, tzinfo=timezone.utc)
LIMA = {"latitude": -12.05, "longitude": -77.04, "accuracy_km": 10}
MADRID = {"latitude": 40.42, "longitude": -3.70, "accuracy_km": 10}


def event(**changes):
    fields = {
        "event_id": "e-1", "account": "test", "outcome": "success",
        "occurred_at": NOW, "device_id": "known", "network": "direct", "location": MADRID,
    }
    return AccessEvent.model_validate(fields | changes)


def sample(at, device="known"):
    return AccessLog(
        occurred_at=at, device_id=device, network="direct",
        latitude=LIMA["latitude"], longitude=LIMA["longitude"], accuracy_km=LIMA["accuracy_km"],
    )


@pytest.mark.parametrize(("network", "accuracy", "expected_score"), [
    ("direct", 10, 60), ("vpn", 10, 0), ("proxy", 10, 0), ("unknown", 10, 0), ("direct", 90, 0),
])
def test_geographic_velocity_requires_precise_direct_connections(network, accuracy, expected_score):
    prior = sample(NOW - timedelta(minutes=10))
    current = event(network=network, location=MADRID | {"accuracy_km": accuracy})
    score, signals = evaluate(current, [prior], timezone.utc, 0, None)
    assert score == expected_score
    assert [signal.code for signal in signals] == (["geo_velocity"] if expected_score else [])


def test_new_device_and_unusual_hour_need_individual_history():
    prior = [sample(NOW - timedelta(days=day, hours=6)) for day in (1, 2, 3)]
    current = event(network="vpn", device_id="new")
    assert evaluate(current, prior[:2], timezone.utc, 0, None) == (0, [])
    score, signals = evaluate(current, prior, timezone.utc, 0, None)
    assert score == 50
    assert [signal.code for signal in signals] == ["unusual_hour", "new_device"]


def test_midnight_wrap_and_missing_device_are_handled():
    midnight = NOW.replace(hour=0)
    prior = [sample(midnight - timedelta(days=day, hours=1), device=None) for day in (1, 2, 3)]
    current = event(occurred_at=midnight, device_id="new", location=None)
    assert evaluate(current, prior, timezone.utc, 0, None) == (0, [])


def test_ip_matches_apply_to_failed_attempts_and_scores_are_capped():
    history = [sample(NOW - timedelta(minutes=10))]
    score, signals = evaluate(event(outcome="failure"), history, timezone.utc, 8, 42)
    assert score == 60
    assert [signal.code for signal in signals] == ["ioc_match"]
    score, signals = evaluate(event(), history, timezone.utc, 5, 42)
    assert score == 100
    assert [signal.code for signal in signals] == ["ioc_match", "failure_burst", "geo_velocity"]


def test_source_timestamps_and_ip_formats_are_validated():
    with pytest.raises(ValidationError, match="zona horaria"):
        event(occurred_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        event(location=MADRID | {"accuracy_km": 0})
    with pytest.raises(ValidationError):
        event(source_ip="fe80::1%eth0")
    assert str(event(source_ip="::ffff:192.0.2.10").source_ip) == "192.0.2.10"
    assert str(AccessIoCInput(ip_address="::ffff:192.0.2.10", reference="prueba", ttl_days=2).ip_address) == "192.0.2.10"
