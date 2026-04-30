from __future__ import annotations

import joblib
import numpy as np
from fastapi.testclient import TestClient

from sklearn_pickle_server.app import create_app
from sklearn_pickle_server.config import Settings


class SumEstimator:
    def predict(self, values):
        return np.asarray(values).sum(axis=1)


class FailingEstimator:
    def predict(self, values):
        raise RuntimeError("not today")


def test_health_does_not_require_loaded_model(tmp_path):
    app = create_app(Settings(model_path=tmp_path / "missing.pkl"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_loaded_model_metadata(tmp_path):
    model_path = tmp_path / "model.pkl"
    joblib.dump(SumEstimator(), model_path)
    app = create_app(Settings(model_path=model_path))

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["model_path"] == str(model_path)
    assert response.json()["model_type"].endswith(".SumEstimator")


def test_ready_reports_missing_model(tmp_path):
    app = create_app(Settings(model_path=tmp_path / "missing.pkl"))

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert "not found" in response.json()["detail"]


def test_predict_returns_configured_response_key(tmp_path):
    model_path = tmp_path / "model.pkl"
    joblib.dump(SumEstimator(), model_path)
    app = create_app(Settings(model_path=model_path, response_key="scores"))

    with TestClient(app) as client:
        response = client.post("/predict", json={"features": [[1, 2, 3], [4, 5, 6]]})

    assert response.status_code == 200
    assert response.json() == {"scores": [6, 15]}


def test_predict_rejects_invalid_json(tmp_path):
    model_path = tmp_path / "model.pkl"
    joblib.dump(SumEstimator(), model_path)
    app = create_app(Settings(model_path=model_path))

    with TestClient(app) as client:
        response = client.post(
            "/predict",
            content="not-json",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 400


def test_predict_rejects_invalid_request_shape(tmp_path):
    model_path = tmp_path / "model.pkl"
    joblib.dump(SumEstimator(), model_path)
    app = create_app(Settings(model_path=model_path, input_mode="dataframe"))

    with TestClient(app) as client:
        response = client.post("/predict", json=[[1, 2, 3]])

    assert response.status_code == 422
    assert "list input must contain objects" in response.json()["detail"]


def test_predict_reports_estimator_failure(tmp_path):
    model_path = tmp_path / "model.pkl"
    joblib.dump(FailingEstimator(), model_path)
    app = create_app(Settings(model_path=model_path))

    with TestClient(app) as client:
        response = client.post("/predict", json=[[1, 2, 3]])

    assert response.status_code == 500
    assert "Model inference failed" in response.json()["detail"]


def test_predict_reports_unready_model(tmp_path):
    app = create_app(Settings(model_path=tmp_path / "missing.pkl"))

    with TestClient(app) as client:
        response = client.post("/predict", json=[[1, 2, 3]])

    assert response.status_code == 503
