"""
Integration tests for the Control Plane API.

These tests run against a throwaway PostgreSQL database and the real MinIO instance.
Requires: `make infra-up` to be running.
"""

import httpx
import pickle

import pytest

from src.infrastructure.observability.grafana import HttpGrafanaDashboardClient

async def upload_bytes(url: str, payload: bytes) -> None:
    async with httpx.AsyncClient(trust_env=False) as storage_client:
        response = await storage_client.put(url, content=payload, headers={"content-type": "application/octet-stream"})
    assert response.status_code in {200, 201, 204}


async def download_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(trust_env=False) as storage_client:
        response = await storage_client.get(url)
    response.raise_for_status()
    return response.content


@pytest.mark.asyncio
class TestAuthAPI:
    async def test_login_preflight_is_allowed_for_local_dashboard_origin(self, anonymous_client):
        response = await anonymous_client.options(
            "/api/v1/users:login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "POST" in response.headers["access-control-allow-methods"]

    async def test_register_login_and_get_profile(self, anonymous_client):
        register_response = await anonymous_client.post(
            "/api/v1/users:register",
            json={
                "email": "auth-user@example.com",
                "password": "AuthPass123",
            },
        )
        assert register_response.status_code == 201
        register_data = register_response.json()
        assert register_data["email"] == "auth-user@example.com"
        assert "id" not in register_data

        login_response = await anonymous_client.post(
            "/api/v1/users:login",
            json={
                "email": "auth-user@example.com",
                "password": "AuthPass123",
            },
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        profile_response = await anonymous_client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert profile_response.status_code == 200
        profile_data = profile_response.json()
        assert profile_data["email"] == "auth-user@example.com"
        assert "id" not in profile_data

    async def test_protected_routes_require_authentication(self, anonymous_client):
        response = await anonymous_client.get("/api/v1/datasets")

        assert response.status_code == 401

    async def test_api_key_can_be_issued_exchanged_and_revoked(self, client, anonymous_client):
        profile_response = await client.get("/api/v1/users/me")
        assert profile_response.status_code == 200
        email = profile_response.json()["email"]

        create_key_response = await client.post(
            "/api/v1/users/me/api-keys",
            json={"name": "sdk"},
        )
        assert create_key_response.status_code == 201
        key_data = create_key_response.json()
        assert key_data["name"] == "sdk"
        assert len(key_data["prefix"]) == 12
        assert key_data["api_key"].startswith("mlp_")

        list_keys_response = await client.get("/api/v1/users/me/api-keys")
        assert list_keys_response.status_code == 200
        assert list_keys_response.json()[0]["name"] == key_data["name"]
        assert list_keys_response.json()[0]["prefix"] == key_data["prefix"]
        assert "api_key" not in list_keys_response.json()[0]

        exchange_response = await anonymous_client.post(
            "/api/v1/users:login_with_api_key",
            json={"email": email, "api_key": key_data["api_key"]},
        )
        assert exchange_response.status_code == 200
        exchange_data = exchange_response.json()
        assert exchange_data["token_type"] == "bearer"

        auth_response = await anonymous_client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {exchange_data['access_token']}"},
        )
        assert auth_response.status_code == 200

        revoke_response = await client.post(f"/api/v1/users/me/api-keys/{key_data['name']}:revoke")
        assert revoke_response.status_code == 200
        assert revoke_response.json() == {"status": "ok"}

        rejected_exchange = await anonymous_client.post(
            "/api/v1/users:login_with_api_key",
            json={"email": email, "api_key": key_data["api_key"]},
        )
        assert rejected_exchange.status_code == 401

    async def test_openapi_advertises_bearer_security_only_for_protected_endpoints(self, anonymous_client):
        response = await anonymous_client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        security_schemes = schema["components"]["securitySchemes"]
        assert "BearerAuth" in security_schemes
        assert schema["paths"]["/api/v1/datasets"]["get"]["security"] == [{"BearerAuth": []}]
        assert schema["paths"]["/api/v1/users:login_with_api_key"]["post"].get("security") is None


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_returns_healthy(self, client):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"


@pytest.mark.asyncio
class TestModelRegistryAPI:
    async def test_create_repository(self, client):
        response = await client.post("/api/v1/repositories", json={
            "name": "test-repo-integration",
            "labels": {"env": "test"},
        })
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-repo-integration"
        assert data["slug"] == "test-repo-integration"
        assert data["labels"] == {"env": "test"}
        assert data["is_deleted"] is False
        assert "created_at" in data

    async def test_list_repositories(self, client):
        # Create one first
        await client.post("/api/v1/repositories", json={
            "name": "test-list-repo",
        })
        response = await client.get("/api/v1/repositories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_repository_by_id(self, client):
        create_resp = await client.post("/api/v1/repositories", json={
            "name": "test-get-repo",
        })
        repo_slug = create_resp.json()["slug"]
        response = await client.get(f"/api/v1/repositories/{repo_slug}")
        assert response.status_code == 200
        assert response.json()["slug"] == repo_slug

    async def test_get_repository_not_found(self, client):
        response = await client.get("/api/v1/repositories/nonexistent-repository")
        assert response.status_code == 404

    async def test_delete_repository(self, client):
        create_resp = await client.post("/api/v1/repositories", json={
            "name": "test-delete-repo",
        })
        repo_slug = create_resp.json()["slug"]
        delete_resp = await client.delete(f"/api/v1/repositories/{repo_slug}")
        assert delete_resp.status_code == 204

        # Verify it's gone (soft-deleted)
        get_resp = await client.get(f"/api/v1/repositories/{repo_slug}")
        assert get_resp.status_code == 404

    async def test_create_model_in_repository(self, client):
        repo_resp = await client.post("/api/v1/repositories", json={
            "name": "test-model-repo",
        })
        repo_slug = repo_resp.json()["slug"]

        model_resp = await client.post(f"/api/v1/repositories/{repo_slug}/models", json={
            "name": "test-model",
            "version": "1.0",
            "labels": {"framework": "pytorch"},
        })
        assert model_resp.status_code == 201
        data = model_resp.json()
        assert data["name"] == "test-model"
        assert data["version"] == "1.0"
        assert data["repository_slug"] == repo_slug
        assert data["status"] == "PENDING"
        assert data["file_type"] == "undefined"

    async def test_list_models_in_repository(self, client):
        repo_resp = await client.post("/api/v1/repositories", json={
            "name": "test-list-model-repo",
        })
        repo_slug = repo_resp.json()["slug"]

        await client.post(f"/api/v1/repositories/{repo_slug}/models", json={
            "name": "model-a",
            "version": "1.0",
        })
        await client.post(f"/api/v1/repositories/{repo_slug}/models", json={
            "name": "model-b",
            "version": "2.0",
        })

        response = await client.get(f"/api/v1/repositories/{repo_slug}/models")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_model_upload_url(self, client):
        repo_resp = await client.post("/api/v1/repositories", json={
            "name": "test-upload-url-repo",
        })
        repo_slug = repo_resp.json()["slug"]

        model_resp = await client.post(f"/api/v1/repositories/{repo_slug}/models", json={
            "name": "upload-model",
            "version": "1.0",
        })

        upload_resp = await client.post(
            f"/api/v1/repositories/{repo_slug}/models/1.0:upload",
            json={"file_name": "crappy-shit.pkl"},
        )
        assert upload_resp.status_code == 200
        data = upload_resp.json()
        assert "upload_url" in data
        assert data["repository_slug"] == repo_slug
        assert data["version"] == "1.0"
        assert "models" in data["upload_url"]  # Verify it targets the models bucket
        assert "crappy-shit.pkl" in data["upload_url"]

    async def test_confirm_upload_marks_model_ready_and_enables_download(self, client):
        repo_resp = await client.post("/api/v1/repositories", json={
            "name": "test-confirm-model-repo",
        })
        repo_slug = repo_resp.json()["slug"]

        await client.post(f"/api/v1/repositories/{repo_slug}/models", json={
            "name": "pickle-model",
            "version": "1.0",
        })
        upload_resp = await client.post(
            f"/api/v1/repositories/{repo_slug}/models/1.0:upload",
            json={"file_name": "pickle-model.pkl"},
        )
        upload_url = upload_resp.json()["upload_url"]
        payload = pickle.dumps({"model": "integration", "version": "1.0"})
        await upload_bytes(upload_url, payload)

        object_key = upload_url.split("/models/", maxsplit=1)[1].split("?", maxsplit=1)[0]
        confirm_resp = await client.post(
            "/api/v1/models:confirm_upload",
            json={"Records": [{"s3": {"object": {"key": object_key}}}]},
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json() == {"status": "ok"}

        model_resp = await client.get(f"/api/v1/repositories/{repo_slug}/models/1.0")
        assert model_resp.status_code == 200
        assert model_resp.json()["status"] == "READY"
        assert model_resp.json()["file_type"] == "pickle"

        download_resp = await client.get(f"/api/v1/repositories/{repo_slug}/models/1.0:download")
        assert download_resp.status_code == 200
        download_url = download_resp.json()["download_url"]
        downloaded = await download_bytes(download_url)
        assert downloaded == payload

    async def test_confirm_upload_reuses_existing_ready_status_without_unique_conflict(self, client):
        repo_resp = await client.post("/api/v1/repositories", json={"name": "test-multi-confirm-repo"})
        repo_slug = repo_resp.json()["slug"]

        for version in ("1.0", "2.0"):
            create_resp = await client.post(
                f"/api/v1/repositories/{repo_slug}/models",
                json={"name": "status-reuse-model", "version": version},
            )
            assert create_resp.status_code == 201

            upload_resp = await client.post(
                f"/api/v1/repositories/{repo_slug}/models/{version}:upload",
                json={"file_name": f"status-reuse-model-v{version}.pkl"},
            )
            assert upload_resp.status_code == 200
            upload_url = upload_resp.json()["upload_url"]
            object_key = upload_url.split("/models/", maxsplit=1)[1].split("?", maxsplit=1)[0]
            await upload_bytes(upload_url, pickle.dumps({"version": version}))

            confirm_resp = await client.post(
                "/api/v1/models:confirm_upload",
                json={"Records": [{"s3": {"object": {"key": object_key}}}]},
            )
            assert confirm_resp.status_code == 200
            assert confirm_resp.json() == {"status": "ok"}

            model_resp = await client.get(f"/api/v1/repositories/{repo_slug}/models/{version}")
            assert model_resp.status_code == 200
            assert model_resp.json()["status"] == "READY"
            assert model_resp.json()["file_type"] == "pickle"

    async def test_get_model_by_id(self, client):
        repo_resp = await client.post("/api/v1/repositories", json={
            "name": "test-get-model-repo",
        })
        repo_slug = repo_resp.json()["slug"]

        model_resp = await client.post(f"/api/v1/repositories/{repo_slug}/models", json={
            "name": "get-model",
            "version": "1.0",
        })

        response = await client.get(f"/api/v1/repositories/{repo_slug}/models/1.0")
        assert response.status_code == 200
        assert response.json()["repository_slug"] == repo_slug
        assert response.json()["version"] == "1.0"
        assert response.json()["status"] == "PENDING"
        assert response.json()["file_type"] == "undefined"


@pytest.mark.asyncio
class TestFeatureRegistryAPI:
    async def test_initiate_dataset_upload(self, client):
        response = await client.post("/api/v1/datasets:upload", json={
            "name": "test-dataset",
            "file_type": "csv",
            "labels": {"source": "test"},
        })
        assert response.status_code == 201
        data = response.json()
        assert data["dataset_slug"] == "test-dataset"
        assert "upload_url" in data
        assert data["version"] >= 1
        assert "datasets" in data["upload_url"]  # Verify targets datasets bucket

    async def test_list_datasets(self, client):
        await client.post("/api/v1/datasets:upload", json={
            "name": "test-list-dataset",
            "file_type": "parquet",
        })
        response = await client.get("/api/v1/datasets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_dataset_by_id(self, client):
        create_resp = await client.post("/api/v1/datasets:upload", json={
            "name": "test-get-dataset",
            "file_type": "csv",
        })
        dataset_slug = create_resp.json()["dataset_slug"]
        version = create_resp.json()["version"]
        response = await client.get(f"/api/v1/datasets/{dataset_slug}/versions/{version}")
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == dataset_slug
        assert data["version"] == version
        assert data["status"] == "PENDING"

    async def test_dataset_versioning(self, client):
        """Uploading the same dataset name should auto-increment version."""
        resp1 = await client.post("/api/v1/datasets:upload", json={
            "name": "versioned-dataset",
            "file_type": "parquet",
        })
        resp2 = await client.post("/api/v1/datasets:upload", json={
            "name": "versioned-dataset",
            "file_type": "parquet",
        })
        assert resp1.json()["version"] == 1
        assert resp2.json()["version"] == 2

    async def test_download_url_not_found_when_no_ready_dataset(self, client):
        response = await client.get("/api/v1/datasets/nonexistent-dataset:download")
        assert response.status_code == 404

    async def test_confirm_upload_marks_dataset_ready_and_enables_download(self, client):
        create_resp = await client.post("/api/v1/datasets:upload", json={
            "name": "confirmed-dataset",
            "file_type": "parquet",
        })
        dataset_slug = create_resp.json()["dataset_slug"]
        dataset_version = create_resp.json()["version"]
        upload_url = create_resp.json()["upload_url"]
        object_key = upload_url.split("/datasets/", maxsplit=1)[1].split("?", maxsplit=1)[0]
        payload = b"PAR1integration-datasetPAR1"

        await upload_bytes(upload_url, payload)

        confirm_resp = await client.post("/api/v1/datasets:confirm_upload", json={
            "Records": [{"s3": {"object": {"key": object_key}}}],
        })
        assert confirm_resp.status_code == 200
        assert confirm_resp.json() == {"status": "ok"}

        dataset_resp = await client.get(f"/api/v1/datasets/{dataset_slug}/versions/{dataset_version}")
        assert dataset_resp.status_code == 200
        assert dataset_resp.json()["status"] == "READY"

        download_resp = await client.get("/api/v1/datasets/confirmed-dataset:download")
        assert download_resp.status_code == 200
        assert await download_bytes(download_resp.json()["download_url"]) == payload

        version_download_resp = await client.get(
            f"/api/v1/datasets/{dataset_slug}/versions/{dataset_version}:download"
        )
        assert version_download_resp.status_code == 200
        assert await download_bytes(version_download_resp.json()["download_url"]) == payload


@pytest.mark.asyncio
class TestExperimentTrackingAPI:
    async def _create_ready_dataset(self, client, name: str) -> tuple[str, int]:
        create_resp = await client.post("/api/v1/datasets:upload", json={
            "name": name,
            "file_type": "parquet",
        })
        dataset_slug = create_resp.json()["dataset_slug"]
        dataset_version = create_resp.json()["version"]
        upload_url = create_resp.json()["upload_url"]
        object_key = upload_url.split("/datasets/", maxsplit=1)[1].split("?", maxsplit=1)[0]

        await upload_bytes(upload_url, b"PAR1trackingPAR1")
        confirm_resp = await client.post("/api/v1/datasets:confirm_upload", json={
            "Records": [{"s3": {"object": {"key": object_key}}}],
        })
        assert confirm_resp.status_code == 200
        return dataset_slug, dataset_version

    async def test_create_list_and_get_experiment(self, client):
        create_resp = await client.post("/api/v1/experiments", json={
            "name": "integration-experiment",
            "logged_data_template": ["loss", "accuracy", "loss"],
            "labels": {"suite": "integration"},
        })
        assert create_resp.status_code == 201
        experiment = create_resp.json()
        assert experiment["slug"] == "integration-experiment"
        assert experiment["logged_data_template"] == ["loss", "accuracy"]
        assert experiment["run_count"] == 0

        list_resp = await client.get("/api/v1/experiments")
        assert list_resp.status_code == 200
        assert any(item["slug"] == "integration-experiment" for item in list_resp.json())

        get_resp = await client.get("/api/v1/experiments/integration-experiment")
        assert get_resp.status_code == 200
        assert get_resp.json()["labels"] == {"suite": "integration"}

    async def test_start_run_with_dataset_log_steps_and_read_plots(self, client):
        dataset_slug, dataset_version = await self._create_ready_dataset(client, "tracking-dataset")
        experiment_resp = await client.post("/api/v1/experiments", json={
            "name": "tracking-experiment",
            "logged_data_template": ["loss", "accuracy"],
        })
        assert experiment_resp.status_code == 201
        experiment_slug = experiment_resp.json()["slug"]

        run_resp = await client.post(f"/api/v1/experiments/{experiment_slug}/runs", json={
            "dataset_slug": dataset_slug,
            "dataset_version": dataset_version,
            "labels": {"stage": "train"},
        })
        assert run_resp.status_code == 201
        assert run_resp.json()["dataset"] == {"dataset_slug": dataset_slug, "version": dataset_version}
        assert run_resp.json()["run_number"] == 1

        log_resp = await client.post(
            f"/api/v1/experiments/{experiment_slug}/runs/1/steps",
            json={
                "items": [
                    {"step": 0, "logged_data": {"loss": 1.0}},
                    {"step": 1, "logged_data": {"loss": 0.8}},
                    {"step": 1, "logged_data": {"loss": 0.7, "accuracy": 0.9}},
                ]
            },
        )
        assert log_resp.status_code == 200

        run_get_resp = await client.get(f"/api/v1/experiments/{experiment_slug}/runs/1")
        assert run_get_resp.status_code == 200
        assert run_get_resp.json()["latest_metrics"] == {"loss": 0.7, "accuracy": 0.9}

        metrics_resp = await client.get(f"/api/v1/experiments/{experiment_slug}/metrics")
        assert metrics_resp.status_code == 200
        assert metrics_resp.json() == {"metrics": ["loss", "accuracy"]}

        run_plot_resp = await client.get(f"/api/v1/experiments/{experiment_slug}/runs/1/plots/loss")
        assert run_plot_resp.status_code == 200
        assert [point["step"] for point in run_plot_resp.json()["points"]] == [0, 1]

        experiment_plot_resp = await client.get(f"/api/v1/experiments/{experiment_slug}/plots/loss")
        assert experiment_plot_resp.status_code == 200
        assert experiment_plot_resp.json()["series"][0]["run"] == {
            "experiment_slug": experiment_slug,
            "run_number": 1,
        }

    async def test_terminal_transition_blocks_further_logging(self, client):
        experiment_resp = await client.post("/api/v1/experiments", json={
            "name": "terminal-experiment",
            "logged_data_template": ["loss"],
        })
        experiment_slug = experiment_resp.json()["slug"]

        run_resp = await client.post(f"/api/v1/experiments/{experiment_slug}/runs", json={})
        assert run_resp.status_code == 201

        complete_resp = await client.post(f"/api/v1/experiments/{experiment_slug}/runs/1:complete")
        assert complete_resp.status_code == 200
        assert complete_resp.json()["status"] == "COMPLETED"

        log_resp = await client.post(
            f"/api/v1/experiments/{experiment_slug}/runs/1/steps",
            json={"items": [{"step": 2, "logged_data": {"loss": 0.2}}]},
        )
        assert log_resp.status_code == 409

    async def test_model_creation_uses_public_run_reference(self, client):
        experiment_resp = await client.post("/api/v1/experiments", json={
            "name": "model-link-experiment",
            "logged_data_template": ["loss"],
        })
        experiment_slug = experiment_resp.json()["slug"]
        run_resp = await client.post(f"/api/v1/experiments/{experiment_slug}/runs", json={})
        assert run_resp.status_code == 201

        repo_resp = await client.post("/api/v1/repositories", json={"name": "model-link-repo"})
        repo_slug = repo_resp.json()["slug"]
        model_resp = await client.post(f"/api/v1/repositories/{repo_slug}/models", json={
            "name": "model-link",
            "version": "1.0",
            "run": {"experiment_slug": experiment_slug, "run_number": 1},
        })
        assert model_resp.status_code == 201
        assert model_resp.json()["run"] == {"experiment_slug": experiment_slug, "run_number": 1}

    async def test_run_dashboard_crud(self, client, monkeypatch):
        async def fake_upsert(self, **kwargs):
            return kwargs["grafana_uid"] or "grafana-run-plot"

        async def fake_delete(self, grafana_uid: str):
            return None

        monkeypatch.setattr(HttpGrafanaDashboardClient, "upsert_run_plot", fake_upsert)
        monkeypatch.setattr(HttpGrafanaDashboardClient, "delete_dashboard", fake_delete)
        monkeypatch.setattr(
            HttpGrafanaDashboardClient,
            "build_solo_iframe_url",
            lambda self, grafana_uid: f"http://grafana.local/d-solo/{grafana_uid}/run-plot?panelId=1",
        )

        experiment_resp = await client.post("/api/v1/experiments", json={
            "name": "dashboard-experiment",
            "logged_data_template": ["loss", "accuracy"],
        })
        experiment_slug = experiment_resp.json()["slug"]
        run_resp = await client.post(f"/api/v1/experiments/{experiment_slug}/runs", json={})
        assert run_resp.status_code == 201

        create_resp = await client.post(
            f"/api/v1/experiments/{experiment_slug}/runs/1/dashboards",
            json={"title": "Loss plot", "plot_type": "line", "metrics": ["loss"]},
        )
        assert create_resp.status_code == 201
        dashboard_id = create_resp.json()["id"]
        assert create_resp.json()["iframe_url"].endswith("grafana-run-plot/run-plot?panelId=1")

        list_resp = await client.get(f"/api/v1/experiments/{experiment_slug}/runs/1/dashboards")
        assert list_resp.status_code == 200
        assert list_resp.json()[0]["title"] == "Loss plot"

        update_resp = await client.patch(
            f"/api/v1/experiments/{experiment_slug}/runs/1/dashboards/{dashboard_id}",
            json={"title": "Accuracy stat", "plot_type": "stat", "metrics": ["accuracy"], "display_order": 0},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["plot_type"] == "stat"
        assert update_resp.json()["metrics"] == ["accuracy"]

        delete_resp = await client.delete(f"/api/v1/experiments/{experiment_slug}/runs/1/dashboards/{dashboard_id}")
        assert delete_resp.status_code == 204

        list_after_delete = await client.get(f"/api/v1/experiments/{experiment_slug}/runs/1/dashboards")
        assert list_after_delete.status_code == 200
        assert list_after_delete.json() == []
