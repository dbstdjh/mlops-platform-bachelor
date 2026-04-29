from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pandas as pd
import pytest

from mldlc import (
    AuthenticationError,
    ConflictError,
    DatasetReadyTimeoutError,
    MLDLC,
    ModelVersion,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


def build_client(control_handler, artifact_handler=None, **kwargs) -> MLDLC:
    control_client = httpx.Client(transport=httpx.MockTransport(control_handler))
    artifact_client = httpx.Client(transport=httpx.MockTransport(artifact_handler or default_artifact_handler))
    return MLDLC(
        "user@example.com",
        "mlp_secret",
        base_url="http://testserver",
        poll_interval=0,
        ready_timeout=0,
        _control_plane_client=control_client,
        _artifact_client=artifact_client,
        **kwargs,
    )


def json_response(payload, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def default_artifact_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "PUT":
        return httpx.Response(200)
    if request.method == "GET":
        return httpx.Response(200, content=b"artifact")
    return httpx.Response(500)


def dataset_payload(status: str = "READY") -> dict:
    return {
        "name": "events",
        "slug": "events",
        "version": 1,
        "status": status,
        "file_type": "parquet",
        "created_at": "2026-01-01T00:00:00Z",
        "labels": {},
    }


def model_payload(status: str = "READY") -> dict:
    return {
        "repository_slug": "fraud",
        "name": "classifier",
        "version": "1.0",
        "run": None,
        "is_deleted": False,
        "s3_uri": "s3://models/user/fraud/classifier/v1.0",
        "status": status,
        "file_type": "pickle",
        "created_at": "2026-01-01T00:00:00Z",
        "labels": {},
    }


def test_authentication_is_lazy_and_cached():
    calls = {"login": 0, "datasets": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users:login_with_api_key"):
            calls["login"] += 1
            return json_response({"access_token": "jwt-token"})
        if request.url.path.endswith("/datasets"):
            calls["datasets"] += 1
            assert request.headers["Authorization"] == "Bearer jwt-token"
            return json_response([])
        return httpx.Response(404)

    client = build_client(handler)
    try:
        assert client.list_datasets() == []
        assert client.list_datasets() == []
    finally:
        client.close()

    assert calls == {"login": 1, "datasets": 2}


def test_request_refreshes_jwt_once_after_401():
    calls = {"login": 0, "experiments": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users:login_with_api_key"):
            calls["login"] += 1
            return json_response({"access_token": f"jwt-{calls['login']}"})
        if request.url.path.endswith("/experiments"):
            calls["experiments"] += 1
            if calls["experiments"] == 1:
                assert request.headers["Authorization"] == "Bearer jwt-1"
                return json_response({"detail": "Unauthorized"}, status_code=401)
            assert request.headers["Authorization"] == "Bearer jwt-2"
            return json_response([])
        return httpx.Response(404)

    client = build_client(handler)
    try:
        assert client.list_experiments() == []
    finally:
        client.close()

    assert calls == {"login": 2, "experiments": 2}


def test_authentication_error_is_raised_for_invalid_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users:login_with_api_key"):
            return json_response({"detail": "Invalid credentials"}, status_code=401)
        return httpx.Response(500)

    client = build_client(handler)
    try:
        with pytest.raises(AuthenticationError):
            client.list_datasets()
    finally:
        client.close()


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, UnauthorizedError),
        (404, NotFoundError),
        (409, ConflictError),
        (422, ValidationError),
    ],
)
def test_error_mapping(status_code: int, expected_error: type[Exception]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users:login_with_api_key"):
            return json_response({"access_token": "jwt-token"})
        if request.url.path.endswith("/datasets"):
            return json_response({"detail": f"status-{status_code}"}, status_code=status_code)
        return httpx.Response(404)

    client = build_client(handler)
    try:
        with pytest.raises(expected_error):
            client.list_datasets()
    finally:
        client.close()


def test_upload_dataset_times_out_when_webhook_confirmation_never_arrives():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users:login_with_api_key"):
            return json_response({"access_token": "jwt-token"})
        if request.url.path.endswith("/datasets:upload"):
            return json_response(
                {
                    "dataset_slug": "events",
                    "upload_url": "http://storage.test/datasets/user/events/v1.parquet?sig=1",
                    "version": 1,
                },
                status_code=201,
            )
        if request.url.path.endswith("/datasets/events/versions/1"):
            return json_response(dataset_payload(status="PENDING"))
        return httpx.Response(404)

    client = build_client(handler)
    try:
        with pytest.raises(DatasetReadyTimeoutError):
            client.upload_dataset("events", pd.DataFrame({"x": [1]}), wait=True, timeout=0)
    finally:
        client.close()


def test_log_model_completes_full_model_lifecycle():
    calls = {"create": 0, "upload": 0, "confirm": 0, "get": 0}

    def control_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users:login_with_api_key"):
            return json_response({"access_token": "jwt-token"})
        if request.url.path.endswith("/repositories/fraud/models") and request.method == "POST":
            calls["create"] += 1
            body = request.read().decode()
            assert '"version":"1.0"' in body
            return json_response(model_payload(status="PENDING"), status_code=201)
        if request.url.path.endswith("/repositories/fraud/models/1.0:upload"):
            calls["upload"] += 1
            assert request.read().decode() == '{"file_name":"classifier-v1.0.pkl"}'
            return json_response(
                {
                    "repository_slug": "fraud",
                    "version": "1.0",
                    "upload_url": "http://storage.test/models/user/fraud/classifier/classifier-v1.0.pkl?sig=1",
                }
            )
        if request.url.path.endswith("/repositories/fraud/models/1.0:confirm_upload"):
            calls["confirm"] += 1
            return json_response({"status": "ok"})
        if request.url.path.endswith("/repositories/fraud/models/1.0"):
            calls["get"] += 1
            return json_response(model_payload(status="READY"))
        return httpx.Response(404)

    uploaded = {}

    def artifact_handler(request: httpx.Request) -> httpx.Response:
        uploaded["bytes"] = request.read()
        return httpx.Response(200)

    client = build_client(control_handler, artifact_handler)
    try:
        result = client.log_model("fraud", "classifier", "1.0", {"weights": [1, 2, 3]})
    finally:
        client.close()

    assert isinstance(result, ModelVersion)
    assert result.status == "READY"
    assert result.file_type == "pickle"
    assert uploaded["bytes"]
    assert calls == {"create": 1, "upload": 1, "confirm": 1, "get": 1}
