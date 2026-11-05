"""Importación reproducible de registros reales publicados por Loghub."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.models import Alert, Integration
from app.models.enums import AlertStatus, SeverityLevel, SourceType

DATASET_ID = "loghub-openssh-2k"
SOURCE_NAME = "Loghub OpenSSH · registros reales"
DATA_DIR = Path(__file__).resolve().parents[2] / "datasets" / "loghub-openssh"
LINE_RE = re.compile(
    r"^(?P<timestamp>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+sshd\[(?P<pid>\d+)\]:\s*(?P<message>.*)$"
)


def load_source(directory: Path = DATA_DIR) -> tuple[dict, list[str]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
    content = (directory / "OpenSSH_2k.log").read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest["sha256"]:
        raise ValueError("La huella SHA-256 del dataset no coincide con el manifiesto")
    lines = content.decode("utf-8").splitlines()
    if len(lines) != manifest["records"]:
        raise ValueError("El número de registros no coincide con el manifiesto")
    return manifest, lines


def parse_line(line: str) -> dict:
    match = LINE_RE.fullmatch(line)
    if not match:
        raise ValueError("Formato OpenSSH no reconocido")
    fields = match.groupdict()
    message = fields["message"]
    lower = message.lower()
    if lower.startswith("failed password") or "authentication failure" in lower:
        event_type, level, severity = "authentication_failed", 7, SeverityLevel.MEDIUM
    elif "invalid user" in lower:
        event_type, level, severity = "invalid_user", 5, SeverityLevel.LOW
    elif lower.startswith("accepted "):
        event_type, level, severity = "authentication_accepted", 1, SeverityLevel.INFO
    elif "possible break-in attempt" in lower:
        event_type, level, severity = "reverse_dns_warning", 5, SeverityLevel.LOW
    elif "connection closed" in lower or "disconnected" in lower or "disconnecting" in lower:
        event_type, level, severity = "connection_closed", 1, SeverityLevel.INFO
    else:
        event_type, level, severity = "other", 1, SeverityLevel.INFO
    address = None
    for candidate in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", message):
        try:
            address = str(ipaddress.ip_address(candidate))
            break
        except ValueError:
            continue
    user_match = re.search(
        r"(?:Failed password for (?:invalid user )?|Accepted \S+ for |[Ii]nvalid user |invalid user )([^\s;]+)", message
    )
    if not user_match:
        user_match = re.search(r"(?:^|\s)user=([^\s;]+)", message)
    return {
        **fields, "event_type": event_type, "source_ip": address,
        "username": user_match.group(1) if user_match else None,
        "rule_level": level, "severity": severity,
    }


async def import_dataset(db) -> dict:
    manifest, lines = load_source()
    # Serializa imports concurrentes sin duplicar el contador ni el manifiesto.
    await db.execute(text("SELECT pg_advisory_xact_lock(784124560)"))
    now = datetime.now(timezone.utc)
    rows = []
    for number, line in enumerate(lines, 1):
        event = parse_line(line)
        fingerprint = hashlib.sha256(f"{DATASET_ID}:{manifest['sha256']}:{number}".encode()).hexdigest()
        rows.append({
            "alert_fingerprint": fingerprint, "external_id": f"{DATASET_ID}:{number}",
            "source_type": SourceType.API, "source_name": SOURCE_NAME,
            "rule_id": f"openssh.{event['event_type']}", "rule_level": event["rule_level"],
            "rule_description": event["message"], "rule_groups": ["openssh", "public_dataset", event["event_type"]],
            "severity": event["severity"], "severity_raw": event["rule_level"],
            "status": AlertStatus.PENDING, "source_ip": event["source_ip"],
            "agent_name": event["host"], "protocol": "ssh", "full_log": line,
            "occurred_at": now,
            "raw_payload": {
                "data_origin": "public_dataset", "dataset_id": DATASET_ID,
                "source_sha256": manifest["sha256"], "source_commit": manifest["commit"],
                "source_line": number, "original_timestamp": event["timestamp"],
                "timestamp_semantics": "ingestion_time; original year and timezone unknown",
                "event_type": event["event_type"], "username": event["username"],
                "host": event["host"], "pid": event["pid"], "ground_truth": None,
                "classification_method": "openssh-parser-v1; deterministic text rules, not attack ground truth",
                "original_line": line,
            },
        })
    added = 0
    for start in range(0, len(rows), 250):
        result = await db.execute(insert(Alert).values(rows[start:start + 250])
                                  .on_conflict_do_nothing(index_elements=[Alert.alert_fingerprint])
                                  .returning(Alert.id))
        added += len(result.scalars().all())
    integration = (await db.execute(select(Integration).where(Integration.code == DATASET_ID))).scalar_one_or_none()
    if integration is None:
        integration = Integration(code=DATASET_ID, name=SOURCE_NAME, category="public_dataset", is_enabled=True)
        db.add(integration)
    integration.base_url = manifest["homepage"]
    integration.config = {**manifest, "last_import": now.isoformat(), "last_added": added,
                          "last_skipped": len(rows) - added, "parser_version": "openssh-parser-v1"}
    integration.last_ok_at = now
    integration.last_error = None
    await db.flush()
    return {"dataset_id": DATASET_ID, "imported": added, "skipped": len(rows) - added,
            "source_records": len(rows), "sha256": manifest["sha256"]}


async def dataset_summary(db) -> dict:
    manifest, _ = load_source()
    events = (await db.execute(select(Alert.id, Alert.source_ip, Alert.raw_payload, Alert.full_log)
                              .where(Alert.source_name == SOURCE_NAME, Alert.deleted_at.is_(None))
                              .order_by(Alert.id))).all()
    integration = (await db.execute(select(Integration).where(Integration.code == DATASET_ID))).scalar_one_or_none()
    event_types, addresses, users, days = Counter(), Counter(), Counter(), Counter()
    entries = []
    for id_, address, payload, full_log in events:
        event_types[payload["event_type"]] += 1
        if address:
            addresses[str(address)] += 1
        if payload.get("username"):
            users[payload["username"]] += 1
        days[payload["original_timestamp"].rsplit(" ", 1)[0]] += 1
        entries.append({"id": id_, "line": payload["source_line"], "timestamp": payload["original_timestamp"],
                        "event_type": payload["event_type"], "username": payload.get("username"),
                        "source_ip": str(address) if address else None, "full_log": full_log})
    counts = lambda counter: [{"name": name, "count": count} for name, count in counter.most_common()]
    legacy_count = (await db.execute(select(func.count(Alert.id)).where(
        Alert.source_name.is_distinct_from(SOURCE_NAME), Alert.deleted_at.is_(None)))).scalar_one()
    return {"manifest": manifest, "imported_records": len(events), "other_records": legacy_count,
            "last_import": integration.config.get("last_import") if integration else None,
            "event_types": counts(event_types), "top_ips": counts(addresses)[:10],
            "top_users": counts(users)[:10], "unique_ips": len(addresses), "unique_users": len(users),
            "original_days": counts(days), "sample": entries[:20], "parser_version": "openssh-parser-v1"}


if __name__ == "__main__":
    import asyncio
    from app.db.session import AsyncSessionLocal

    async def main():
        async with AsyncSessionLocal() as db:
            result = await import_dataset(db)
            await db.commit()
            print(json.dumps(result))
    asyncio.run(main())
