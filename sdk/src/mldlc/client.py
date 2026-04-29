from __future__ import annotations

import time
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd
from pydantic import BaseModel

from mldlc.errors import (
    APIError,
    AuthenticationError,
    ConflictError,
    DatasetReadyTimeoutError,
    NotFoundError,
    SerializationError,
    UnauthorizedError,
    ValidationError,
)
from mldlc.models import (
    DatasetVersion,
    ExperimentInfo,
    ModelRepositoryInfo,
    ModelVersion,
    RunInfo,
    RunRef,
)
from mldlc.run_context import RunContext
from mldlc.serialization import (
    DatasetAsType,
    deserialize_dataset,
    infer_model_artifact_file_name,
    serialize_dataset,
    serialize_model_artifact,
    write_payload,
)


class _AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MLDLC:
    """Sync-first data scientist client for the MLDLC platform."""

    def __init__(
        self,
        username: str,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        ready_timeout: float = 60.0,
        poll_interval: float = 1.0,
        *,
        _control_plane_client=None,
        _artifact_client: httpx.Client | None = None,
    ) -> None:
        self.username = username
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.ready_timeout = ready_timeout
        self.poll_interval = poll_interval
        self._api_url = f"{self.base_url}/api/v1"
        self._owns_control_plane_client = _control_plane_client is None
        self._owns_artifact_client = _artifact_client is None
        self._control_plane_client = _control_plane_client or httpx.Client(timeout=timeout, trust_env=False)
        self._artifact_client = _artifact_client or httpx.Client(timeout=timeout, trust_env=False)
        self._access_token: str | None = None

    def __enter__(self) -> "MLDLC":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._owns_control_plane_client and hasattr(self._control_plane_client, "close"):
            self._control_plane_client.close()
        if (
            self._owns_artifact_client
            and self._artifact_client is not self._control_plane_client
            and hasattr(self._artifact_client, "close")
        ):
            self._artifact_client.close()

    def _url(self, path: str) -> str:
        return f"{self._api_url}{path}"

    def _authenticate(self, *, force_refresh: bool = False) -> None:
        if self._access_token is not None and not force_refresh:
            return

        response = self._control_plane_client.post(
            self._url("/users:login_with_api_key"),
            json={"email": self.username, "api_key": self.api_key},
        )
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key credentials")
        self._raise_for_response(response)
        token = _AccessTokenResponse.model_validate(response.json())
        self._access_token = token.access_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
        retry_on_401: bool = True,
    ):
        headers: dict[str, str] = {"accept": "application/json"}
        if authenticated:
            self._authenticate()
            headers["Authorization"] = f"Bearer {self._access_token}"

        response = self._control_plane_client.request(
            method,
            self._url(path),
            json=json,
            params=params,
            headers=headers,
        )

        if authenticated and response.status_code == 401 and retry_on_401:
            self._authenticate(force_refresh=True)
            headers["Authorization"] = f"Bearer {self._access_token}"
            response = self._control_plane_client.request(
                method,
                self._url(path),
                json=json,
                params=params,
                headers=headers,
            )

        self._raise_for_response(response)
        return response

    def _response_detail(self, response) -> str:
        try:
            payload = response.json()
        except Exception:
            text = getattr(response, "text", "")
            return text or f"Request failed with status {response.status_code}"

        if isinstance(payload, dict) and "detail" in payload:
            detail = payload["detail"]
            if isinstance(detail, str):
                return detail
        return str(payload)

    def _raise_for_response(self, response) -> None:
        status_code = response.status_code
        if 200 <= status_code < 300:
            return

        detail = self._response_detail(response)
        if status_code == 401:
            raise UnauthorizedError(detail)
        if status_code == 404:
            raise NotFoundError(detail)
        if status_code == 409:
            raise ConflictError(detail)
        if status_code == 422:
            raise ValidationError(detail)
        raise APIError(detail)

    def _get_json(self, method: str, path: str, **kwargs):
        return self._request(method, path, **kwargs).json()

    def _upload_to_signed_url(self, upload_url: str, payload: bytes) -> None:
        response = self._artifact_client.put(
            upload_url,
            content=payload,
            headers={"content-type": "application/octet-stream"},
        )
        if response.status_code not in {200, 201, 204}:
            raise APIError(f"Artifact upload failed with status {response.status_code}")

    def _download_from_signed_url(self, download_url: str) -> bytes:
        response = self._artifact_client.get(download_url)
        if response.status_code != 200:
            raise APIError(f"Artifact download failed with status {response.status_code}")
        return response.content

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _normalize_dataset_ref(self, dataset) -> tuple[str | None, int | None]:
        if dataset is None:
            return None, None
        if isinstance(dataset, DatasetVersion):
            return dataset.slug, dataset.version
        if isinstance(dataset, tuple) and len(dataset) == 2:
            return dataset[0], dataset[1]
        raise SerializationError("dataset must be a DatasetVersion or (dataset_slug, version) tuple")

    def _normalize_run_ref(self, run) -> RunRef | None:
        if run is None:
            return None
        if isinstance(run, RunContext):
            return run.ref
        if isinstance(run, RunInfo):
            return RunRef(experiment_slug=run.experiment_slug, run_number=run.run_number)
        if isinstance(run, RunRef):
            return run
        if isinstance(run, tuple) and len(run) == 2:
            return RunRef(experiment_slug=run[0], run_number=run[1])
        raise SerializationError("run must be a RunContext, RunInfo, RunRef, or (experiment_slug, run_number)")

    def _model_from_json(self, model_type, payload):
        return model_type.model_validate(payload)

    def create_experiment(
        self,
        name: str,
        metrics: list[str],
        labels: dict[str, Any] | None = None,
    ) -> ExperimentInfo:
        payload = self._get_json(
            "POST",
            "/experiments",
            json={"name": name, "logged_data_template": metrics, "labels": labels or {}},
        )
        return self._model_from_json(ExperimentInfo, payload)

    def list_experiments(self) -> list[ExperimentInfo]:
        payload = self._get_json("GET", "/experiments")
        return [self._model_from_json(ExperimentInfo, item) for item in payload]

    def get_experiment(self, experiment_slug: str) -> ExperimentInfo:
        payload = self._get_json("GET", f"/experiments/{experiment_slug}")
        return self._model_from_json(ExperimentInfo, payload)

    def start_run(self, experiment_slug: str, *, dataset=None, labels: dict[str, Any] | None = None) -> RunContext:
        return RunContext(self, experiment_slug, dataset=dataset, labels=labels)

    def _start_run(self, experiment_slug: str, *, dataset=None, labels: dict[str, Any] | None = None) -> RunInfo:
        dataset_slug, dataset_version = self._normalize_dataset_ref(dataset)
        payload = self._get_json(
            "POST",
            f"/experiments/{experiment_slug}/runs",
            json={
                "dataset_slug": dataset_slug,
                "dataset_version": dataset_version,
                "labels": labels or {},
            },
        )
        return self._model_from_json(RunInfo, payload)

    def list_runs(self, experiment_slug: str) -> list[RunInfo]:
        payload = self._get_json("GET", f"/experiments/{experiment_slug}/runs")
        return [self._model_from_json(RunInfo, item) for item in payload]

    def get_run(self, experiment_slug: str, run_number: int) -> RunInfo:
        payload = self._get_json("GET", f"/experiments/{experiment_slug}/runs/{run_number}")
        return self._model_from_json(RunInfo, payload)

    def _append_run_steps(self, experiment_slug: str, run_number: int, items: list[dict[str, Any]]) -> None:
        normalized_items = []
        for item in items:
            step_payload = {"step": item["step"], "logged_data": item["logged_data"]}
            timestamp = item.get("timestamp")
            if timestamp is not None:
                step_payload["timestamp"] = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
            normalized_items.append(step_payload)
        self._request(
            "POST",
            f"/experiments/{experiment_slug}/runs/{run_number}/steps",
            json={"items": normalized_items},
        )

    def _complete_run(self, experiment_slug: str, run_number: int) -> RunInfo:
        payload = self._get_json("POST", f"/experiments/{experiment_slug}/runs/{run_number}:complete")
        return self._model_from_json(RunInfo, payload)

    def _fail_run(self, experiment_slug: str, run_number: int) -> RunInfo:
        payload = self._get_json("POST", f"/experiments/{experiment_slug}/runs/{run_number}:fail")
        return self._model_from_json(RunInfo, payload)

    def get_run_metric_history(self, experiment_slug: str, run_number: int, metric_name: str) -> pd.DataFrame:
        payload = self._get_json("GET", f"/experiments/{experiment_slug}/runs/{run_number}/plots/{metric_name}")
        return pd.DataFrame(
            [
                {
                    "experiment_slug": experiment_slug,
                    "run_number": run_number,
                    "metric_name": payload["metric_name"],
                    "step": point["step"],
                    "value": point["val"],
                    "timestamp": point["timestamp"],
                }
                for point in payload["points"]
            ]
        )

    def get_experiment_metric_history(self, experiment_slug: str, metric_name: str) -> pd.DataFrame:
        payload = self._get_json("GET", f"/experiments/{experiment_slug}/plots/{metric_name}")
        rows = []
        for series in payload["series"]:
            for point in series["points"]:
                rows.append(
                    {
                        "experiment_slug": series["run"]["experiment_slug"],
                        "run_number": series["run"]["run_number"],
                        "metric_name": payload["metric_name"],
                        "step": point["step"],
                        "value": point["val"],
                        "timestamp": point["timestamp"],
                    }
                )
        return pd.DataFrame(rows)

    def list_datasets(self) -> list[DatasetVersion]:
        payload = self._get_json("GET", "/datasets")
        return [self._model_from_json(DatasetVersion, item) for item in payload]

    def get_dataset(self, dataset_slug: str, version: int) -> DatasetVersion:
        payload = self._get_json("GET", f"/datasets/{dataset_slug}/versions/{version}")
        return self._model_from_json(DatasetVersion, payload)

    def _wait_for_dataset_ready(self, dataset_slug: str, version: int, timeout: float | None = None) -> DatasetVersion:
        resolved_timeout = self.ready_timeout if timeout is None else timeout
        deadline = time.monotonic() + resolved_timeout
        while True:
            dataset = self.get_dataset(dataset_slug, version)
            if dataset.status == "READY":
                return dataset
            if time.monotonic() >= deadline:
                raise DatasetReadyTimeoutError(
                    f"Dataset '{dataset_slug}' version {version} did not become READY within {resolved_timeout} seconds"
                )
            self._sleep(self.poll_interval)

    def upload_dataset(
        self,
        name: str,
        data,
        *,
        labels: dict[str, Any] | None = None,
        file_type: str | None = None,
        wait: bool = True,
        timeout: float | None = None,
    ) -> DatasetVersion:
        payload, resolved_type = serialize_dataset(data, file_type=file_type)
        upload = self._get_json(
            "POST",
            "/datasets:upload",
            json={"name": name, "file_type": resolved_type, "labels": labels or {}},
        )
        self._upload_to_signed_url(upload["upload_url"], payload)
        if wait:
            return self._wait_for_dataset_ready(upload["dataset_slug"], upload["version"], timeout=timeout)
        return self.get_dataset(upload["dataset_slug"], upload["version"])

    def _resolve_latest_ready_dataset(self, dataset_slug: str) -> DatasetVersion:
        datasets = [item for item in self.list_datasets() if item.slug == dataset_slug and item.status == "READY"]
        if not datasets:
            raise NotFoundError(f"No ready dataset found with slug '{dataset_slug}'")
        return max(datasets, key=lambda item: item.version)

    def download_dataset(
        self,
        dataset_slug: str,
        version: int | None = None,
        *,
        as_type: DatasetAsType = "auto",
        destination: str | Path | None = None,
    ):
        metadata = self._resolve_latest_ready_dataset(dataset_slug) if version is None else self.get_dataset(dataset_slug, version)
        path = (
            f"/datasets/{dataset_slug}:download"
            if version is None
            else f"/datasets/{dataset_slug}/versions/{version}:download"
        )
        payload = self._get_json("GET", path)
        content = self._download_from_signed_url(payload["download_url"])
        return deserialize_dataset(content, metadata.file_type, as_type=as_type, destination=destination)

    def create_repository(self, name: str, labels: dict[str, Any] | None = None) -> ModelRepositoryInfo:
        payload = self._get_json("POST", "/repositories", json={"name": name, "labels": labels or {}})
        return self._model_from_json(ModelRepositoryInfo, payload)

    def list_repositories(self) -> list[ModelRepositoryInfo]:
        payload = self._get_json("GET", "/repositories")
        return [self._model_from_json(ModelRepositoryInfo, item) for item in payload]

    def get_repository(self, repository_slug: str) -> ModelRepositoryInfo:
        payload = self._get_json("GET", f"/repositories/{repository_slug}")
        return self._model_from_json(ModelRepositoryInfo, payload)

    def delete_repository(self, repository_slug: str) -> None:
        self._request("DELETE", f"/repositories/{repository_slug}")

    def list_models(self, repository_slug: str) -> list[ModelVersion]:
        payload = self._get_json("GET", f"/repositories/{repository_slug}/models")
        return [self._model_from_json(ModelVersion, item) for item in payload]

    def get_model(self, repository_slug: str, version: str) -> ModelVersion:
        payload = self._get_json("GET", f"/repositories/{repository_slug}/models/{version}")
        return self._model_from_json(ModelVersion, payload)

    def log_model(
        self,
        repository_slug: str,
        name: str,
        version: str,
        artifact,
        *,
        run=None,
        labels: dict[str, Any] | None = None,
        serializer: str = "auto",
        file_name: str | None = None,
    ) -> ModelVersion:
        run_ref = self._normalize_run_ref(run)
        artifact_bytes = serialize_model_artifact(artifact, serializer=serializer)
        upload_file_name = infer_model_artifact_file_name(
            artifact,
            name=name,
            version=version,
            serializer=serializer,
            file_name=file_name,
        )
        self._request(
            "POST",
            f"/repositories/{repository_slug}/models",
            json={
                "name": name,
                "version": version,
                "run": None if run_ref is None else run_ref.model_dump(),
                "labels": labels or {},
            },
        )
        upload = self._get_json(
            "POST",
            f"/repositories/{repository_slug}/models/{version}:upload",
            json={"file_name": upload_file_name},
        )
        self._upload_to_signed_url(upload["upload_url"], artifact_bytes)
        self._request("POST", f"/repositories/{repository_slug}/models/{version}:confirm_upload")
        return self.get_model(repository_slug, version)

    def download_model(
        self,
        repository_slug: str,
        version: str,
        *,
        destination: str | Path | None = None,
        loader: Callable[[Path], Any] | None = None,
    ):
        payload = self._get_json("GET", f"/repositories/{repository_slug}/models/{version}:download")
        content = self._download_from_signed_url(payload["download_url"])
        model = self.get_model(repository_slug, version)
        default_destination = destination
        if default_destination is None:
            original_name = None
            if model.s3_uri:
                original_name = model.s3_uri.rsplit("/", maxsplit=1)[-1]
            if original_name:
                temp_dir = Path(tempfile.mkdtemp(prefix=f"mldlc-{repository_slug}-{model.name}-v{version}-"))
                default_destination = write_payload(content, temp_dir / original_name, None)
            else:
                default_destination = write_payload(
                    content,
                    None,
                    None,
                    prefix=f"mldlc-{repository_slug}-{model.name}-v{version}-",
                )
        else:
            default_destination = write_payload(content, default_destination, None)
        if loader is not None:
            return loader(Path(default_destination))
        return Path(default_destination)

    @staticmethod
    def _signed_url_object_key(signed_url: str, bucket: str) -> str:
        parsed = urlparse(signed_url)
        marker = f"/{bucket}/"
        if marker not in parsed.path:
            raise SerializationError(f"Signed URL does not point to the expected '{bucket}' bucket")
        return parsed.path.split(marker, maxsplit=1)[1]
