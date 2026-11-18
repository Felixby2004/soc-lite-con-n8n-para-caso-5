from dataclasses import replace

import pytest

from app.schemas.access_ml import ModelConfiguration
from app.services.access_ml_data import chronological_split, simulated_rows, utc_day
from app.services.access_ml_predict import explain_prediction, probability
from app.services.access_ml_training import arrays, make_model, temporal_folds, train_model


def test_simulated_partitions_and_nested_folds_preserve_day_boundaries():
    development, validation, test = chronological_split(simulated_rows())
    assert [len(part) for part in (development, validation, test)] == [840, 180, 180]
    assert utc_day(development[-1]) < utc_day(validation[0])
    assert utc_day(validation[-1]) < utc_day(test[0])
    outer = list(temporal_folds(development, 5))
    assert len(outer) == 5
    for _, train, held_out in outer:
        assert utc_day(train[-1]) < utc_day(held_out[0])
        for _, inner_train, inner_val in temporal_folds(train, 3):
            assert utc_day(inner_train[-1]) < utc_day(inner_val[0])
            assert utc_day(inner_val[-1]) < utc_day(held_out[0])


def test_minimum_temporal_dataset_can_form_all_nested_folds():
    development, _, _ = chronological_split(simulated_rows()[:13 * 12])
    folds = list(temporal_folds(development, 5, 4))
    assert len(folds) == 5
    assert len(list(temporal_folds(folds[0][1], 3))) == 3


@pytest.mark.parametrize("algorithm", ["logistic", "tree"])
def test_optuna_trials_and_portable_artifact_reproduce_prediction(algorithm):
    rows = simulated_rows()
    config = ModelConfiguration(algorithm=algorithm, trials=3)
    trials = []
    result, artifact = train_model(rows, len(rows), config, trials.append)
    assert len(trials) == 18 and {trial["fold"] for trial in trials} == set(range(1, 7))
    assert all(len(trial["inner_scores"]) == 3 for trial in trials)
    assert sum(result["model"]["confusion"].values()) == 180
    assert result["paired"]["replicates"] == 2000

    development, _, test = chronological_split(rows)
    model = make_model(config, result["best_params"]).fit(*arrays(development))
    x, _ = arrays(test)
    assert [probability(artifact, row.features) for row in test] == pytest.approx(model.predict_proba(x)[:, 1])
    prediction = explain_prediction(artifact, test[0].features, result["model"]["threshold"])
    assert len(prediction["contributions"]) == len(test[0].features)


def test_test_labels_do_not_change_training_or_threshold():
    rows = simulated_rows()
    development, validation, test = chronological_split(rows)
    changed = development + validation + [replace(row, label=1 - row.label) for row in test]
    config = ModelConfiguration(trials=3)
    original, original_artifact = train_model(rows, len(rows), config, lambda _: None)
    revised, revised_artifact = train_model(changed, len(changed), config, lambda _: None)
    assert original_artifact == revised_artifact
    assert original["model"]["threshold"] == revised["model"]["threshold"]
    assert original["outer_folds"] == revised["outer_folds"]
    assert original["dataset_sha256"] != revised["dataset_sha256"]
