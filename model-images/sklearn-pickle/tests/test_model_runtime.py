from __future__ import annotations

import pickle

import joblib
import numpy as np
import pandas as pd
import pytest

from sklearn_pickle_server.config import Settings
from sklearn_pickle_server.model_runtime import (
    InputNormalizationError,
    ModelLoadError,
    PredictionError,
    load_model,
    normalize_input,
    predict,
    to_jsonable,
)


class EchoEstimator:
    def predict(self, values):
        return np.asarray(values).sum(axis=1)

    def predict_proba(self, values):
        rows = len(values)
        return np.tile(np.array([[0.25, 0.75]]), (rows, 1))

    def transform(self, values):
        return pd.DataFrame({"score": np.asarray(values).sum(axis=1)})


class CallableEstimator:
    def __call__(self, values):
        return {"rows": len(values)}


class FailingEstimator:
    def predict(self, values):
        raise ValueError("boom")


def test_load_model_uses_joblib_artifact(tmp_path):
    model_path = tmp_path / "model.pkl"
    joblib.dump(EchoEstimator(), model_path)

    bundle = load_model(model_path)

    assert bundle.model_path == model_path
    assert bundle.model_type.endswith(".EchoEstimator")
    assert isinstance(bundle.model, EchoEstimator)


def test_load_model_falls_back_to_pickle(tmp_path, monkeypatch):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(pickle.dumps(EchoEstimator()))
    monkeypatch.setattr(joblib, "load", lambda path: (_ for _ in ()).throw(ValueError("nope")))

    bundle = load_model(model_path)

    assert isinstance(bundle.model, EchoEstimator)


def test_load_model_reports_missing_artifact(tmp_path):
    with pytest.raises(ModelLoadError, match="not found"):
        load_model(tmp_path / "missing.pkl")


def test_auto_normalize_list_payload_to_two_dimensional_array():
    result = normalize_input([1, 2, 3], Settings())

    assert result.shape == (1, 3)
    assert result.tolist() == [[1, 2, 3]]


def test_auto_normalize_named_features_to_dataframe():
    result = normalize_input({"age": 42, "income": 1000}, Settings())

    assert list(result.columns) == ["age", "income"]
    assert result.to_dict(orient="records") == [{"age": 42, "income": 1000}]


def test_auto_normalize_enveloped_features():
    result = normalize_input(
        {"features": [{"age": 42, "income": 1000}]},
        Settings(),
    )

    assert isinstance(result, pd.DataFrame)
    assert result.to_dict(orient="records") == [{"age": 42, "income": 1000}]


def test_input_key_extracts_configured_payload():
    result = normalize_input(
        {"payload": [[1, 2], [3, 4]]},
        Settings(input_key="payload"),
    )

    assert result.tolist() == [[1, 2], [3, 4]]


def test_dataframe_mode_rejects_non_object_lists():
    with pytest.raises(InputNormalizationError, match="list input must contain objects"):
        normalize_input([[1, 2]], Settings(input_mode="dataframe"))


def test_predict_method_dispatch():
    model = EchoEstimator()

    assert predict(model, np.array([[1, 2]]), "predict").tolist() == [3]
    assert predict(model, np.array([[1, 2]]), "predict_proba").tolist() == [[0.25, 0.75]]
    assert predict(CallableEstimator(), [1, 2, 3], "call") == {"rows": 3}


def test_predict_reports_missing_method():
    with pytest.raises(PredictionError, match="does not expose"):
        predict(EchoEstimator(), [[1, 2]], "decision_function")


def test_predict_wraps_estimator_errors():
    with pytest.raises(PredictionError, match="Model inference failed"):
        predict(FailingEstimator(), [[1, 2]], "predict")


def test_to_jsonable_handles_numpy_and_pandas_values():
    payload = {
        "array": np.array([[1, 2]]),
        "scalar": np.int64(4),
        "series": pd.Series([5, 6]),
        "frame": pd.DataFrame({"x": [7]}),
    }

    assert to_jsonable(payload) == {
        "array": [[1, 2]],
        "scalar": 4,
        "series": [5, 6],
        "frame": [{"x": 7}],
    }
