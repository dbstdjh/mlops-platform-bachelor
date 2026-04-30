.PHONY: kube-up kube-down kube-reset kube-logs kube-status kube-namespace kube-schema kube-secrets kube-validate api-dev dashboard-dev test test-unit test-integration test-e2e test-control-plane test-sdk test-dashboard test-dashboard-unit test-dashboard-integration test-dashboard-e2e test-model-images build-sklearn-pickle-image push-sklearn-pickle-image publish-prebuilt-images sdk-example-iris-lifecycle sdk-example-multi-run-comparison sdk-example-dense-metrics-per-step sdk-example-long-history-batched-steps sdk-example-detached-model-workflows sdk-examples

KUBECTL ?= minikube kubectl --
MINIKUBE ?= minikube
NAMESPACE ?= mldlc
K8S_SECRET_ENV ?= k8s/base/secret.env
PREBUILT_REGISTRY ?= gitea.mldlc.local
PREBUILT_OWNER ?= mldlc
SKLEARN_PICKLE_IMAGE_NAME ?= sklearn-pickle-server
SKLEARN_PICKLE_VERSION ?= 0.1.0
SKLEARN_PICKLE_LOCAL_IMAGE ?= mldlc/sklearn-pickle-server:dev
SKLEARN_PICKLE_REGISTRY_IMAGE ?= $(PREBUILT_REGISTRY)/$(PREBUILT_OWNER)/$(SKLEARN_PICKLE_IMAGE_NAME)

# ─── Kubernetes Infrastructure ────────────────────────────────────
kube-namespace:
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -

kube-schema: kube-namespace
	$(KUBECTL) -n $(NAMESPACE) create configmap db-schema --from-file=data-model.sql --dry-run=client -o yaml | $(KUBECTL) apply -f -

kube-secrets: kube-namespace
	test -f $(K8S_SECRET_ENV) || (printf '%s\n' 'Missing $(K8S_SECRET_ENV). Create it from k8s/base/secret.example.env and fill local values.' && exit 1)
	$(KUBECTL) -n $(NAMESPACE) create secret generic platform-secret --from-env-file=$(K8S_SECRET_ENV) --dry-run=client -o yaml | $(KUBECTL) apply -f -

kube-up: kube-secrets kube-schema
	$(MINIKUBE) addons enable ingress
	$(KUBECTL) -n ingress-nginx patch svc ingress-nginx-controller -p '{"spec":{"type":"LoadBalancer"}}'
	$(MINIKUBE) image build -t mldlc/control-plane:dev ./control-plane
	$(MINIKUBE) image build -t mldlc/dashboard:dev ./dashboard
	$(MINIKUBE) image build -t $(SKLEARN_PICKLE_LOCAL_IMAGE) ./model-images/sklearn-pickle
	$(KUBECTL) apply -k k8s/base
	$(KUBECTL) -n $(NAMESPACE) rollout status statefulset/db --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/minio --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/gitea --timeout=240s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/grafana --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/api --timeout=180s
	$(KUBECTL) -n $(NAMESPACE) rollout status deployment/dashboard --timeout=180s

kube-down:
	$(KUBECTL) delete -k k8s/base --ignore-not-found=true

kube-reset:
	$(KUBECTL) delete namespace $(NAMESPACE) --ignore-not-found=true
	$(KUBECTL) wait --for=delete namespace/$(NAMESPACE) --timeout=180s || true
	$(MAKE) kube-up

kube-logs:
	$(KUBECTL) -n $(NAMESPACE) logs -f deployment/api

kube-status:
	$(KUBECTL) -n $(NAMESPACE) get pods,svc,ingress,pvc,jobs

kube-validate:
	$(KUBECTL) kustomize k8s/base
	$(KUBECTL) apply --dry-run=client -k k8s/base

# ─── Control Plane (local dev, outside Docker) ────────────────────
api-dev:
	cd control-plane && uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

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
	$(MAKE) test-model-images

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

test-model-images:
	cd model-images/sklearn-pickle && uv run pytest -v

test: test-unit test-integration test-e2e
