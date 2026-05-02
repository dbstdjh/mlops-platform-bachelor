.PHONY: kube-up kube-down kube-reset kube-reset-storage kube-logs kube-status kube-namespace kube-schema kube-secrets kube-bootstrap-gitea kube-validate kube-reapply-api kube-reapply-gateway kube-reapply-dashboard api-dev deployment-dev gateway-dev dashboard-dev test test-unit test-integration test-e2e test-control-plane test-sdk test-deployment test-gateway test-dashboard test-dashboard-unit test-dashboard-integration test-dashboard-e2e test-model-images build-sklearn-pickle-image push-sklearn-pickle-image publish-prebuilt-images sdk-example-iris-lifecycle sdk-example-multi-run-comparison sdk-example-dense-metrics-per-step sdk-example-long-history-batched-steps sdk-example-detached-model-workflows sdk-example-deploy-pickle-model sdk-examples

KUBECTL ?= minikube kubectl --
MINIKUBE ?= minikube
NAMESPACE ?= mldlc
K8S_SECRET_ENV ?= k8s/base/secret.env
GITEA_BOOTSTRAP_SCRIPT ?= scripts/bootstrap-gitea.sh
GITEA_ADMIN_USER ?= mldlc-admin
GITEA_ADMIN_EMAIL ?= admin@mldlc.local
GITEA_ADMIN_TOKEN_NAME ?= mldlc-control-plane
GITEA_ADMIN_TOKEN_SCOPES ?= all
PREBUILT_REGISTRY ?= gitea.mldlc.local
PREBUILT_OWNER ?= mldlc
SKLEARN_PICKLE_IMAGE_NAME ?= sklearn-pickle-server
SKLEARN_PICKLE_VERSION ?= 0.1.0
SKLEARN_PICKLE_LOCAL_IMAGE ?= mldlc/sklearn-pickle-server:dev
SKLEARN_PICKLE_REGISTRY_IMAGE ?= $(PREBUILT_REGISTRY)/$(PREBUILT_OWNER)/$(SKLEARN_PICKLE_IMAGE_NAME)
API_IMAGE ?= mldlc/control-plane:dev
GATEWAY_IMAGE ?= mldlc/edge-gateway:dev
DASHBOARD_IMAGE ?= mldlc/dashboard:dev
GO_TEST_FLAGS ?= -v

# ─── Kubernetes Infrastructure ────────────────────────────────────
kube-namespace:
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -

kube-schema: kube-namespace
	$(KUBECTL) -n $(NAMESPACE) create configmap db-schema --from-file=data-model.sql --dry-run=client -o yaml | $(KUBECTL) apply -f -

kube-secrets: kube-namespace
	test -f $(K8S_SECRET_ENV) || (printf '%s\n' 'Missing $(K8S_SECRET_ENV). Create it from k8s/base/secret.example.env and fill local values.' && exit 1)
	$(KUBECTL) -n $(NAMESPACE) create secret generic platform-secret --from-env-file=$(K8S_SECRET_ENV) --dry-run=client -o yaml | $(KUBECTL) apply -f -

kube-bootstrap-gitea:
	KUBECTL="$(KUBECTL)" NAMESPACE="$(NAMESPACE)" GITEA_ADMIN_USER="$(GITEA_ADMIN_USER)" GITEA_ADMIN_EMAIL="$(GITEA_ADMIN_EMAIL)" GITEA_ADMIN_TOKEN_NAME="$(GITEA_ADMIN_TOKEN_NAME)" GITEA_ADMIN_TOKEN_SCOPES="$(GITEA_ADMIN_TOKEN_SCOPES)" $(GITEA_BOOTSTRAP_SCRIPT)

kube-up: kube-secrets kube-schema
	$(MINIKUBE) addons enable ingress
	$(KUBECTL) -n ingress-nginx patch svc ingress-nginx-controller -p '{"spec":{"type":"LoadBalancer"}}'
	$(MINIKUBE) image build -t mldlc/control-plane:dev ./control-plane
	$(MINIKUBE) image build -t $(GATEWAY_IMAGE) ./edge-gateway
	$(MINIKUBE) image build -t mldlc/deployment-service:dev ./deployment-service
	$(MINIKUBE) image build -t mldlc/dashboard:dev ./dashboard
	$(MINIKUBE) image build -t $(SKLEARN_PICKLE_LOCAL_IMAGE) ./model-images/sklearn-pickle
	$(KUBECTL) apply -k k8s/base
	$(KUBECTL) -n $(NAMESPACE) rollout status statefulset/db --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/minio --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) wait --for=condition=complete job/db-init --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) wait --for=condition=complete job/gitea-db-init --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) wait --for=condition=complete job/minio-init --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/gitea --timeout=240s
	$(MAKE) kube-bootstrap-gitea
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/grafana --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/api --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/edge-gateway --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/deployment-service --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/dashboard --timeout=180s

kube-down:
	$(KUBECTL) delete -k k8s/base --ignore-not-found=true

kube-reset:
	$(KUBECTL) delete namespace $(NAMESPACE) --ignore-not-found=true
	$(KUBECTL) wait --for=delete namespace/$(NAMESPACE) --timeout=180s || true
	$(MAKE) kube-reset-storage
	$(MAKE) kube-up

kube-reset-storage:
	@pv_names="$$( $(KUBECTL) get pv -o jsonpath='{range .items[?(@.spec.claimRef.namespace=="$(NAMESPACE)")]}{.metadata.name}{" "}{end}' 2>/dev/null )"; \
	if [ -n "$$pv_names" ]; then \
		printf '%s\n' "Deleting persistent volumes from namespace $(NAMESPACE): $$pv_names"; \
		$(KUBECTL) delete pv $$pv_names --ignore-not-found=true --wait=true; \
	else \
		printf '%s\n' "No persistent volumes remain from namespace $(NAMESPACE)."; \
	fi

kube-logs:
	$(KUBECTL) -n $(NAMESPACE) logs -f deployment/api

kube-status:
	$(KUBECTL) -n $(NAMESPACE) get pods,svc,ingress,pvc,jobs

kube-validate:
	$(KUBECTL) kustomize k8s/base
	$(KUBECTL) apply --dry-run=client -k k8s/base

kube-reapply-api:
	$(MINIKUBE) image build -t $(API_IMAGE) ./control-plane
	$(KUBECTL) -n $(NAMESPACE) apply -f k8s/base/api.yaml
	$(KUBECTL) -n $(NAMESPACE) rollout restart deployment/api
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/api --timeout=180s

kube-reapply-gateway:
	$(MINIKUBE) image build -t $(GATEWAY_IMAGE) ./edge-gateway
	$(KUBECTL) -n $(NAMESPACE) apply -f k8s/base/edge-gateway.yaml
	$(KUBECTL) -n $(NAMESPACE) rollout restart deployment/edge-gateway
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/edge-gateway --timeout=180s

kube-reapply-dashboard:
	$(MINIKUBE) image build -t $(DASHBOARD_IMAGE) ./dashboard
	$(KUBECTL) -n $(NAMESPACE) apply -f k8s/base/dashboard.yaml
	$(KUBECTL) -n $(NAMESPACE) rollout restart deployment/dashboard
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/dashboard --timeout=180s

# ─── Control Plane (local dev, outside Docker) ────────────────────
api-dev:
	cd control-plane && uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

deployment-dev:
	cd deployment-service && uv run python -m deployment_service.main

gateway-dev:
	cd edge-gateway && go run .

# ─── Dashboard (local dev, outside Docker) ────────────────────────
dashboard-dev:
	cd dashboard && npm run dev -- --host 0.0.0.0 --port 5173

# ─── Global Prebuilt Model Images ─────────────────────────────────
build-sklearn-pickle-image:
	docker build -t $(SKLEARN_PICKLE_LOCAL_IMAGE) ./model-images/sklearn-pickle

push-sklearn-pickle-image: build-sklearn-pickle-image
	docker tag $(SKLEARN_PICKLE_LOCAL_IMAGE) $(SKLEARN_PICKLE_REGISTRY_IMAGE):$(SKLEARN_PICKLE_VERSION)
	docker tag $(SKLEARN_PICKLE_LOCAL_IMAGE) $(SKLEARN_PICKLE_REGISTRY_IMAGE):dev
	docker push $(SKLEARN_PICKLE_REGISTRY_IMAGE):$(SKLEARN_PICKLE_VERSION)
	docker push $(SKLEARN_PICKLE_REGISTRY_IMAGE):dev

publish-prebuilt-images: push-sklearn-pickle-image

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

sdk-example-deploy-pickle-model:
	cd sdk && uv run python examples/deploy_pickle_model.py

sdk-examples:
	@printf '%s\n' \
		'Available SDK example targets:' \
		'  make sdk-example-iris-lifecycle' \
		'  make sdk-example-multi-run-comparison' \
		'  make sdk-example-dense-metrics-per-step' \
		'  make sdk-example-long-history-batched-steps' \
		'  make sdk-example-detached-model-workflows' \
		'  make sdk-example-deploy-pickle-model'

# ─── Tests ────────────────────────────────────────────────────────
test-unit:
	cd control-plane && uv run pytest tests/unit -v
	cd sdk && uv run pytest tests/unit -v
	cd deployment-service && uv run pytest tests/unit -v
	$(MAKE) test-gateway
	cd dashboard && npm run test:unit
	$(MAKE) test-model-images

test-integration:
	cd control-plane && uv run pytest tests/integration -v
	cd sdk && uv run pytest tests/integration -v
	cd deployment-service && uv run pytest tests/integration -v
	cd dashboard && npm run test:integration

test-e2e:
	cd control-plane && uv run pytest tests/e2e -v
	cd sdk && uv run pytest tests/e2e -v
	cd dashboard && npm run test:e2e

test-control-plane:
	cd control-plane && uv run pytest tests/ -v

test-sdk:
	cd sdk && uv run pytest tests/ -v

test-deployment:
	cd deployment-service && uv run pytest tests/ -v

test-gateway:
	cd edge-gateway && go test $(GO_TEST_FLAGS) ./...

test-dashboard-unit:
	cd dashboard && npm run test:unit

test-dashboard-integration:
	cd dashboard && npm run test:integration

test-dashboard-e2e:
	cd dashboard && npm run test:e2e

test-dashboard:
	cd dashboard && npm test

test-model-images:
	cd model-images/sklearn-pickle && uv run pytest -v

test: test-unit test-integration test-e2e
