"""Contrasta el puntaje registrado con etiquetas independientes de revisión."""
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessLog, AccessReview
from app.schemas.access_evaluation import AccessConfusion, AccessEvaluation, EvaluationCount, EvaluationScope
from app.services.access_scoring import ALERT_THRESHOLD, MAX_ACCURACY_KM
from app.services.access_service import DEMO_SOURCE

# En la muestra, night simula un acceso de mantenimiento legítimo.
DEMO_EXPECTED = ("known-1", "known-2", "known-3", "known-4", "vpn-control", "night")
SCORE_BANDS = (("0–24", 25), ("25–49", 50), ("50–69", 70), ("70–84", 85), ("85–100", 101))


def evaluation_metrics(matrix: AccessConfusion) -> dict[str, float | None]:
    tp, fp, fn, tn = matrix.true_positive, matrix.false_positive, matrix.false_negative, matrix.true_negative

    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


async def evaluate_accesses(
    db: AsyncSession, scope: EvaluationScope, start: datetime, end: datetime, threshold: int,
) -> AccessEvaluation:
    label = AccessReview.label
    filters = [AccessLog.source != DEMO_SOURCE, AccessLog.occurred_at.between(start, end)]
    if scope == "demo":
        label = case(
            (AccessLog.event_id == "travel", "anomalous"),
            (AccessLog.event_id.in_(DEMO_EXPECTED), "expected"),
        )
        filters = [AccessLog.source == DEMO_SOURCE]

    quality = {
        "IP registrada": AccessLog.source_ip.is_not(None),
        "Dispositivo registrado": AccessLog.device_id.is_not(None),
        "Tipo de conexión conocido": AccessLog.network != "unknown",
        "Ubicación apta para regla geográfica": and_(
            AccessLog.network == "direct",
            AccessLog.latitude.is_not(None),
            AccessLog.longitude.is_not(None),
            AccessLog.accuracy_km <= MAX_ACCURACY_KM,
        ),
    }
    buckets = await db.execute(
        select(
            AccessLog.score, label, func.count(),
            *(func.count().filter(condition) for condition in quality.values()),
        )
        .select_from(AccessLog)
        .outerjoin(AccessReview, AccessReview.access_log_id == AccessLog.id)
        .where(*filters)
        .group_by(AccessLog.score, label)
    )
    bands = [EvaluationCount(label=name) for name, _ in SCORE_BANDS]
    data_quality = [EvaluationCount(label=name) for name in quality]
    result = AccessEvaluation(
        scope=scope, from_at=start if scope == "operation" else None, to_at=end, threshold=threshold,
        live_threshold=ALERT_THRESHOLD, score_bands=bands, data_quality=data_quality,
    )
    for score, review, count, *quality_counts in buckets:
        result.events += count
        for column, value in zip(result.data_quality, quality_counts):
            column.count += value
        for band, (_, upper) in zip(result.score_bands, SCORE_BANDS):
            if score < upper:
                band.count += count
                break
        flagged = score >= threshold
        if flagged:
            result.flagged += count
        if review is not None:
            result.reviewed += count
            if review == "anomalous":
                if flagged:
                    result.confusion.true_positive += count
                else:
                    result.confusion.false_negative += count
            elif flagged:
                result.confusion.false_positive += count
            else:
                result.confusion.true_negative += count

    return result.model_copy(update=evaluation_metrics(result.confusion))
