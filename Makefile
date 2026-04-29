.PHONY: infra-up infra-down infra-logs api-dev test test-unit test-integration test-e2e test-control-plane

# ─── Infrastructure ───────────────────────────────────────────────
infra-up:
	docker compose up -d db minio minio-init gitea grafana

infra-down:
	docker compose down

infra-logs:
	docker compose logs -f

# ─── Control Plane (local dev, outside Docker) ────────────────────
api-dev:
	cd control-plane && uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# ─── Tests ────────────────────────────────────────────────────────
test-unit:
	cd control-plane && uv run pytest tests/unit -v

test-integration:
	cd control-plane && uv run pytest tests/integration -v

test-e2e:
	cd control-plane && uv run pytest tests/e2e -v

test-control-plane:
	cd control-plane && uv run pytest tests/ -v

test: test-unit test-integration test-e2e
