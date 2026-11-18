from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DataScope = Literal["demo", "operation"]
Algorithm = Literal["logistic", "tree"]


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: DataScope = "demo"
    algorithm: Algorithm = "logistic"
    days: int = Field(default=90, ge=14, le=365)
    trials: int = Field(default=8, ge=3, le=25)
    seed: int = Field(default=42, ge=0, le=999999)


class ModelRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    status: Literal["queued", "running", "completed", "failed"]
    configuration: ModelConfiguration


class ModelRunDetail(ModelRunSummary):
    started_at: datetime | None
    finished_at: datetime | None
    progress: dict
    result: dict | None
    error: str | None
