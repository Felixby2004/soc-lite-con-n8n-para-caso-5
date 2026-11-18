"""Búsqueda anidada por bloques temporales y prueba posterior independiente."""
from collections import defaultdict
from typing import Callable, Sequence

import numpy as np
import optuna
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve
from sklearn.model_selection import TimeSeriesSplit
from sklearn.tree import DecisionTreeClassifier

from app.schemas.access_evaluation import AccessConfusion
from app.schemas.access_ml import ModelConfiguration
from app.services.access_evaluation import evaluation_metrics
from app.services.access_ml_data import (
    DEMO_VERSION, FEATURES, INNER_FOLDS, OUTER_FOLDS, TrainingRow, chronological_split, dataset_fingerprint, describe, utc_day,
)
from app.services.access_ml_predict import probability as artifact_probability
from app.services.access_scoring import ALERT_THRESHOLD

def require_classes(rows: Sequence[TrainingRow], context: str) -> None:
    if {row.label for row in rows} != {0, 1}:
        raise ValueError(f"{context} necesita ejemplos esperados y anómalos. Amplía el período o revisa más accesos.")


def temporal_folds(rows: Sequence[TrainingRow], folds: int, min_train_days: int = 1):
    groups = defaultdict(list)
    for row in rows:
        groups[utc_day(row)].append(row)
    days = sorted(groups)
    size = min(len(days) // (folds + 1), (len(days) - min_train_days) // folds)
    for i, (train, validation) in enumerate(TimeSeriesSplit(n_splits=folds, test_size=size).split(days), 1):
        yield i, [row for j in train for row in groups[days[j]]], [row for j in validation for row in groups[days[j]]]


def arrays(rows: Sequence[TrainingRow]):
    return np.asarray([row.features for row in rows]), np.asarray([row.label for row in rows])


def make_model(config: ModelConfiguration, parameters: dict):
    if config.algorithm == "logistic":
        return LogisticRegression(max_iter=600, solver="liblinear", random_state=config.seed, **parameters)
    return DecisionTreeClassifier(random_state=config.seed, **parameters)


def sample_parameters(trial: optuna.Trial, config: ModelConfiguration) -> dict:
    class_weight = trial.suggest_categorical("class_weight", [None, "balanced"])
    if config.algorithm == "logistic":
        return {"C": trial.suggest_float("C", 0.015, 40.0, log=True), "class_weight": class_weight}
    return {
        "max_depth": trial.suggest_int("max_depth", 2, 9),
        "min_samples_leaf": trial.suggest_int("min_samples_leaf", 2, 20),
        "criterion": trial.suggest_categorical("criterion", ["gini", "entropy"]),
        "class_weight": class_weight,
    }


def tune(rows, config, fold: int, record: Callable[[dict], None]) -> optuna.Study:
    splits = []
    for inner, train, validation in temporal_folds(rows, INNER_FOLDS):
        require_classes(train, f"Desarrollo interno {inner} de la búsqueda {fold}")
        require_classes(validation, f"Validación interna {inner} de la búsqueda {fold}")
        splits.append((arrays(train), arrays(validation)))

    def objective(trial: optuna.Trial) -> float:
        parameters = sample_parameters(trial, config)
        scores = []
        for (x_train, y_train), (x_val, y_val) in splits:
            model = make_model(config, parameters).fit(x_train, y_train)
            scores.append(float(average_precision_score(y_val, model.predict_proba(x_val)[:, 1])))
        trial.set_user_attr("inner_scores", scores)
        return float(np.mean(scores))

    def on_trial(study: optuna.Study, trial: optuna.trial.FrozenTrial) -> None:
        record({
            "stage": "outer" if fold <= OUTER_FOLDS else "final",
            "fold": fold, "number": trial.number + 1, "state": trial.state.name,
            "value": trial.value, "best": study.best_value, "params": trial.params,
            "inner_scores": trial.user_attrs.get("inner_scores", []),
        })

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(
        seed=config.seed + fold, n_startup_trials=3,
    ))
    study.optimize(objective, n_trials=config.trials, callbacks=[on_trial])
    return study


def choose_threshold(labels, probabilities) -> float:
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    sums = precision[:-1] + recall[:-1]
    f1 = np.divide(2 * precision[:-1] * recall[:-1], sums, out=np.zeros_like(sums), where=sums != 0)
    return float(thresholds[np.flatnonzero(np.isclose(f1, f1.max(), atol=1e-12, rtol=0))[-1]])


def curve_points(x, y) -> list[dict]:
    indices = np.unique(np.linspace(0, len(x) - 1, min(101, len(x)), dtype=int))
    return [{"x": float(x[i]), "y": float(y[i])} for i in indices]


def evaluate_scores(labels, scores, threshold: float) -> dict:
    flagged = scores >= threshold
    positive = labels == 1
    matrix = AccessConfusion(
        true_positive=int(np.count_nonzero(flagged & positive)),
        false_positive=int(np.count_nonzero(flagged & ~positive)),
        false_negative=int(np.count_nonzero(~flagged & positive)),
        true_negative=int(np.count_nonzero(~flagged & ~positive)),
    )
    fpr, tpr, _ = roc_curve(labels, scores)
    precision, recall, _ = precision_recall_curve(labels, scores)
    return {
        **evaluation_metrics(matrix), "confusion": matrix.model_dump(), "threshold": threshold,
        "accuracy": float(np.mean(flagged == positive)), "roc_auc": float(roc_auc_score(labels, scores)),
        "average_precision": float(average_precision_score(labels, scores)),
        "roc": curve_points(fpr, tpr), "pr": curve_points(recall[::-1], precision[::-1]),
    }


def paired_comparison(rows, labels, probabilities, threshold: float, heuristic, seed: int) -> dict:
    differences = (probabilities >= threshold) == (labels == 1)
    reference = (heuristic >= ALERT_THRESHOLD / 100) == (labels == 1)
    groups: dict[str, list[int]] = defaultdict(list)
    for row, correct, baseline_correct in zip(rows, differences, reference):
        groups[utc_day(row)].append(int(correct) - int(baseline_correct))
    observed = float(np.mean(differences) - np.mean(reference))
    result = {"difference": observed, "days": len(groups), "interval": None, "p_value": None, "replicates": 0}
    if len(groups) < 5:
        return result

    rng = np.random.default_rng(seed)
    sums = np.array([sum(block) for block in groups.values()])
    sizes = np.array([len(block) for block in groups.values()])
    trials = 2_000
    sampled = rng.integers(0, len(groups), size=(trials, len(groups)))
    boot = sums[sampled].sum(axis=1) / sizes[sampled].sum(axis=1)
    shuffled = rng.choice([-1, 1], size=(trials, len(groups))) @ sums
    p = (1 + np.count_nonzero(np.abs(shuffled) >= abs(sums.sum()))) / (trials + 1)
    return {
        **result, "interval": np.quantile(boot, [0.025, 0.975]).tolist(),
        "p_value": float(p), "replicates": trials,
    }


def serialize_model(model, config: ModelConfiguration, development) -> dict:
    artifact = {
        "version": 1, "algorithm": config.algorithm, "features": list(FEATURES),
        "reference": np.median(development, axis=0).tolist(),
    }
    if config.algorithm == "logistic":
        return {**artifact, "coefficients": model.coef_[0].tolist(), "intercept": float(model.intercept_[0])}
    tree = model.tree_
    return {
        **artifact, "left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
        "feature": tree.feature.tolist(), "cut": tree.threshold.tolist(),
        "probability": (tree.value[:, 0, 1] / tree.value[:, 0, :].sum(axis=1)).tolist(),
    }


def train_model(rows, total: int, config: ModelConfiguration, record: Callable[[dict], None]) -> tuple[dict, dict]:
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    development, validation, test = chronological_split(rows)
    for part, name in ((development, "Desarrollo"), (validation, "Validación"), (test, "Prueba")):
        require_classes(part, name)

    folds = []
    for index, train, outer_val in temporal_folds(development, OUTER_FOLDS, INNER_FOLDS + 1):
        require_classes(train, f"Entrenamiento externo {index}")
        require_classes(outer_val, f"Validación externa {index}")
        study = tune(train, config, index, record)
        x_val, y_val = arrays(outer_val)
        model = make_model(config, study.best_params).fit(*arrays(train))
        folds.append({
            "fold": index, "train": describe(train), "validation": describe(outer_val),
            "best_inner_ap": study.best_value,
            "average_precision": float(average_precision_score(y_val, model.predict_proba(x_val)[:, 1])),
            "params": study.best_params,
        })

    final = tune(development, config, OUTER_FOLDS + 1, record)
    x_dev, y_dev = arrays(development)
    model = make_model(config, final.best_params).fit(x_dev, y_dev)
    artifact = serialize_model(model, config, x_dev)
    x_validation, y_validation = arrays(validation)
    validation_scores = [artifact_probability(artifact, values) for values in x_validation]
    threshold = choose_threshold(y_validation, validation_scores)
    x_test, y_test = arrays(test)
    probability = np.asarray([artifact_probability(artifact, values) for values in x_test])
    heuristic = np.asarray([row.heuristic_score / 100 for row in test])
    result = {
        "dataset_sha256": dataset_fingerprint(rows), "total_events": total, "dataset": describe(rows),
        "demo_version": DEMO_VERSION if config.scope == "demo" else None,
        "partitions": {"development": describe(development), "validation": describe(validation), "test": describe(test)},
        "outer_folds": folds, "mean_outer_ap": float(np.mean([fold["average_precision"] for fold in folds])),
        "best_params": final.best_params, "best_inner_ap": final.best_value,
        "model": evaluate_scores(y_test, probability, threshold),
        "heuristic": evaluate_scores(y_test, heuristic, ALERT_THRESHOLD / 100),
        "paired": paired_comparison(test, y_test, probability, threshold, heuristic, config.seed),
        "versions": {"scikit_learn": sklearn.__version__, "optuna": optuna.__version__},
    }
    return result, artifact
