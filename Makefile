.PHONY: infra-up infra-down infra-logs api-dev dashboard-dev test test-unit test-integration test-e2e test-control-plane test-sdk test-dashboard test-dashboard-unit test-dashboard-integration test-dashboard-e2e sdk-example-iris-lifecycle sdk-example-multi-run-comparison sdk-example-dense-metrics-per-step sdk-example-long-history-batched-steps sdk-example-detached-model-workflows sdk-examples

# ─── Infrastructure ───────────────────────────────────────────────
infra-up:
	docker compose up -d db minio minio-init gitea grafana

infra-up-full:
	docker compose up -d

infra-up-full-build:
	docker compose up --build -d

infra-down:
	docker compose down

infra-down-volumes:
	docker compose down -v

infra-db-init:
	docker compose up -d db
	until [ "$$(docker inspect -f '{{.State.Health.Status}}' $$(docker compose ps -q db))" = "healthy" ]; do sleep 1; done
	docker compose exec -T db psql -v ON_ERROR_STOP=1 -U mlops -d mlops < data-model.sql

infra-reset: infra-down-volumes infra-db-init
	docker compose up -d minio minio-init gitea grafana

infra-reset-full: infra-down-volumes infra-db-init
	docker compose up --build -d

infra-logs:
	docker compose logs -f

# ─── Control Plane (local dev, outside Docker) ────────────────────
api-dev:
	cd control-plane && uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# ─── Dashboard (local dev, outside Docker) ────────────────────────
dashboard-dev:
	cd dashboard && npm run dev -- --host 0.0.0.0 --port 5173

# ─── SDK Examples ──────────────────────────────────────────────────
sdk-example-iris-lifecycle:
	cd sdk && uv run python examples/iris_lifecycle.py

sdk-example-multi-run-comparison:
	cd sdk && uv run python examples/multi_run_comparison.py

sdk-example-dense-metrics-per-step:
	cd sdk && uv run python examples/dense_metrics_per_step.py

sdk-example-long-history-batched-steps:
	cd sdk && uv run python examples/long_history_batched_steps.py

sdk-example-detached-model-workflows:
	cd sdk && uv run python examples/detached_model_workflows.py

sdk-examples:
	@printf '%s\n' \
		'Available SDK example targets:' \
		'  make sdk-example-iris-lifecycle' \
		'  make sdk-example-multi-run-comparison' \
		'  make sdk-example-dense-metrics-per-step' \
		'  make sdk-example-long-history-batched-steps' \
		'  make sdk-example-detached-model-workflows'

# ─── Tests ────────────────────────────────────────────────────────
test-unit:
	cd control-plane && uv run pytest tests/unit -v
	cd sdk && uv run pytest tests/unit -v
	cd dashboard && npm run test:unit

test-integration:
	cd control-plane && uv run pytest tests/integration -v
	cd sdk && uv run pytest tests/integration -v
	cd dashboard && npm run test:integration

test-e2e:
	cd control-plane && uv run pytest tests/e2e -v
	cd sdk && uv run pytest tests/e2e -v
	cd dashboard && npm run test:e2e

test-control-plane:
	cd control-plane && uv run pytest tests/ -v

test-sdk:
	cd sdk && uv run pytest tests/ -v

test-dashboard-unit:
	cd dashboard && npm run test:unit

test-dashboard-integration:
	cd dashboard && npm run test:integration

test-dashboard-e2e:
	cd dashboard && npm run test:e2e

test-dashboard:
	cd dashboard && npm test

test: test-unit test-integration test-e2e
