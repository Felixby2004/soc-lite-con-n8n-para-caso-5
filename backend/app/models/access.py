"""Evidencia de acceso e indicadores IP del Caso 5."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str] = mapped_column(String(160))
    account: Mapped[str] = mapped_column(String(160))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(12))
    source_ip: Mapped[str | None] = mapped_column(INET)
    device_id: Mapped[str | None] = mapped_column(String(160))
    network: Mapped[str] = mapped_column(String(12))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    accuracy_km: Mapped[float | None] = mapped_column(Float)
    fingerprint: Mapped[str] = mapped_column(String(64))
    score: Mapped[int] = mapped_column(SmallInteger)
    signals: Mapped[list[dict]] = mapped_column(JSONB)
    baseline_size: Mapped[int] = mapped_column(SmallInteger)


class AccessAnomaly(Base):
    __tablename__ = "access_anomalies"

    access_log_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("access_logs.id", ondelete="CASCADE"), primary_key=True
    )
    alert_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("alerts.id", ondelete="SET NULL"))


class AccessIoC(Base):
    __tablename__ = "access_iocs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ip_address: Mapped[str] = mapped_column(INET, unique=True)
    reference: Mapped[str] = mapped_column(String(240))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessReview(Base):
    __tablename__ = "access_reviews"

    access_log_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("access_logs.id", ondelete="CASCADE"), primary_key=True
    )
    label: Mapped[str] = mapped_column(String(12))
    note: Mapped[str | None] = mapped_column(String(300))
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessModelRun(Base):
    __tablename__ = "access_model_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    requested_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12))
    configuration: Mapped[dict] = mapped_column(JSONB)
    progress: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    artifact: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
