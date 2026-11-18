from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EvaluationScope = Literal["operation", "demo"]
EvaluationFormat = Literal["pdf", "docx", "xlsx"]


class AccessConfusion(BaseModel):
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    true_negative: int = 0


class EvaluationCount(BaseModel):
    label: str
    count: int = 0


class AccessEvaluation(BaseModel):
    scope: EvaluationScope
    from_at: datetime | None
    to_at: datetime
    threshold: int
    live_threshold: int
    events: int = 0
    flagged: int = 0
    reviewed: int = 0
    confusion: AccessConfusion = Field(default_factory=AccessConfusion)
    precision: float | None = None
    recall: float | None = None
    specificity: float | None = None
    f1: float | None = None
    score_bands: list[EvaluationCount]
    data_quality: list[EvaluationCount]
