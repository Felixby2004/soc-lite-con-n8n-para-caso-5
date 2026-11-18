import pytest

from app.models.enums import SeverityLevel
from app.schemas.access_evaluation import AccessConfusion
from app.services.access_evaluation import evaluation_metrics
from app.services.access_scoring import alert_severity


def test_metrics_preserve_the_absence_of_labeled_evidence():
    assert evaluation_metrics(AccessConfusion()) == {
        "precision": None, "recall": None, "specificity": None, "f1": None,
    }
    assert evaluation_metrics(AccessConfusion(true_negative=5)) == {
        "precision": None, "recall": None, "specificity": 1.0, "f1": None,
    }


def test_metrics_count_missed_anomalies_and_false_alerts():
    metrics = evaluation_metrics(AccessConfusion(true_positive=2, false_positive=1, false_negative=3, true_negative=4))
    assert metrics == pytest.approx({"precision": 2 / 3, "recall": 2 / 5, "specificity": 4 / 5, "f1": 1 / 2})


@pytest.mark.parametrize(("score", "severity"), [
    (49, None), (50, SeverityLevel.MEDIUM), (69, SeverityLevel.MEDIUM),
    (70, SeverityLevel.HIGH), (84, SeverityLevel.HIGH), (85, SeverityLevel.CRITICAL),
])
def test_preview_and_ingestion_share_operational_severity(score, severity):
    assert alert_severity(score) == severity
