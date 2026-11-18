from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, IPvAnyAddress, StringConstraints, field_validator

from app.models.enums import SeverityLevel

Identifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160, pattern=r"^[^\x00-\x1f\x7f]+$"),
]
Source = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]


def normalize_ip(value: IPvAnyAddress) -> IPvAnyAddress:
    if getattr(value, "scope_id", None):
        raise ValueError("Ingrese la IP sin identificador de interfaz")
    return getattr(value, "ipv4_mapped", None) or value


HostAddress = Annotated[IPvAnyAddress, AfterValidator(normalize_ip)]


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_km: float = Field(gt=0, le=20_000)


class AccessEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: Identifier
    account: Identifier
    occurred_at: datetime
    outcome: Literal["success", "failure"]
    source_ip: HostAddress | None = None
    device_id: Identifier | None = None
    network: Literal["direct", "vpn", "proxy", "unknown"] = "unknown"
    location: Location | None = None

    @field_validator("occurred_at", mode="before")
    @classmethod
    def validate_timestamp_input(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Use fecha ISO 8601 con zona horaria")
        return value

    @field_validator("occurred_at")
    @classmethod
    def as_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None or not 2000 <= value.year <= 9998:
            raise ValueError("Use fecha ISO 8601 con zona horaria y año a partir de 2000")
        return value.astimezone(timezone.utc)


class AccessBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Source
    events: list[AccessEvent] = Field(min_length=1, max_length=250)


class AccessIoCInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip_address: HostAddress
    reference: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240, pattern=r"^[^\x00-\x1f\x7f]+$"),
    ]
    ttl_days: int = Field(ge=1, le=365)


class Signal(BaseModel):
    code: str
    points: int
    detail: str


class AccessPreview(BaseModel):
    score: int
    signals: list[Signal]
    baseline_size: int
    severity: SeverityLevel | None


class AccessReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["expected", "anomalous"]
    note: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=300, pattern=r"^[^\x00-\x1f\x7f]*$"),
    ] | None = None


class AccessReviewItem(AccessReviewInput):
    model_config = ConfigDict(from_attributes=True)
    reviewed_at: datetime


class AccessLogItem(BaseModel):
    id: int
    source: str
    event_id: str
    account: str
    occurred_at: datetime
    outcome: Literal["success", "failure"]
    source_ip: str | None
    device_id: str | None
    network: Literal["direct", "vpn", "proxy", "unknown"]
    score: int
    signals: list[Signal]
    baseline_size: int
    alert_id: int | None
    is_anomaly: bool
    review: AccessReviewItem | None = None


class AccessIoCItem(BaseModel):
    id: int
    ip_address: str
    reference: str
    expires_at: datetime
    active: bool


class AccessImportResult(BaseModel):
    imported: int = 0
    skipped: int = 0
    anomalies: int = 0


class AccessProfile(BaseModel):
    samples: int
    devices: list[str]
    hours: list[int]
    timezone: str
    window_days: int
    minimum_samples: int


class AccessSummary(BaseModel):
    events: int
    accounts: int
    anomalies: int
    active_iocs: int
    demo_enabled: bool
