"""Predicción de artefactos JSON generados por el trabajador local."""
from math import exp
from struct import pack, unpack
from typing import Sequence

from app.services.access_ml_data import FEATURES


def probability(artifact: dict, features: Sequence[float]) -> float:
    if artifact["version"] != 1 or artifact["features"] != list(FEATURES) or len(features) != len(FEATURES):
        raise ValueError("El artefacto es incompatible con esta versión de las características.")
    if artifact["algorithm"] == "logistic":
        logit = artifact["intercept"] + sum(w * x for w, x in zip(artifact["coefficients"], features, strict=True))
        return 1 / (1 + exp(-logit)) if logit >= 0 else exp(logit) / (1 + exp(logit))

    # Los árboles de scikit-learn comparan las entradas como float32.
    node = 0
    while artifact["left"][node] != -1:
        value = unpack("f", pack("f", features[artifact["feature"][node]]))[0]
        branch = "left" if value <= artifact["cut"][node] else "right"
        node = artifact[branch][node]
    return artifact["probability"][node]


def explain_prediction(artifact: dict, features: Sequence[float], threshold: float) -> dict:
    predicted = probability(artifact, features)
    contributions = []
    for index, (code, name) in enumerate(FEATURES.items()):
        adjusted = list(features)
        adjusted[index] = artifact["reference"][index]
        contributions.append({
            "code": code, "label": name, "value": features[index], "reference": adjusted[index],
            "delta": predicted - probability(artifact, adjusted),
        })
    severity = None
    if predicted >= threshold:
        severity = "critical" if predicted >= 0.85 else "high" if predicted >= 0.70 else "medium"
    return {
        "probability": predicted, "threshold": threshold, "flagged": predicted >= threshold,
        "severity": severity, "contributions": sorted(contributions, key=lambda item: -abs(item["delta"])),
    }
