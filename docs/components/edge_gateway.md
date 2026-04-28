# Edge API Gateway (Go)

The Edge API Gateway is a single Go application that acts as the primary entry point for all model inference traffic. It runs locally alongside the Control Plane API, intercepting requests before they reach the deployed model containers in Minikube.

## Why It Exists

The original architecture considered deploying the API Gateway as a **sidecar** inside every Minikube pod. This was abandoned due to severe networking complexities — Docker-to-Minikube routing loops, CORS challenges, and internal IP resolution issues.

The **Edge Gateway Pattern** replaces the sidecar with a single gateway running outside the cluster:
- All inference traffic routes to `localhost:8080` (the Go gateway).
- The gateway handles authentication, logging, validation, and proxying in one place.
- Zero Kubernetes networking configuration is required.

## Request Flow

```
SDK / React UI
      │
      ▼
  Go Gateway (localhost:8080)
      │
      ├── 1. JWT Validation
      ├── 2. Input Schema Validation
      ├── 3. Proxy to Minikube IP
      ├── 4. Receive Response
      └── 5. Log Request + Response to PostgreSQL
```

## JWT Validation

The gateway validates JWT tokens for every inference request before proxying. This keeps the model containers completely unaware of authentication — they receive only validated, clean requests.

- The gateway shares the same JWT secret as the Control Plane (FastAPI Users).
- If validation fails, the request is rejected at the edge with a `401 Unauthorized`. The model container is never contacted.

## Input Schema Validation (JSON Schema)

When a model is deployed, the Control Plane stores the Pydantic-generated `input_schema` (a standard JSON Schema specification) in the `deployment` table. The Go gateway fetches and caches this schema.

For each inference request:
1. The gateway retrieves the JSON Schema for the target deployment.
2. It validates the incoming request body against the schema using a standard library (e.g., `github.com/santhosh-tekuri/jsonschema/v5`).
3. If validation fails, the request is rejected with a `422 Unprocessable Entity` containing the specific validation errors. The model container is never contacted.

> **Note:** The JSON Schema produced by Pydantic's `model_json_schema()` is a mathematically formal OpenAPI/JSON Schema Core specification. The Go library consumes it natively with zero custom parsing.

## Proxy Routing to Minikube

After authentication and validation, the gateway proxies the request directly to the model container's internal Minikube IP and port. The gateway maintains a mapping of `deployment_id` → `minikube_endpoint` sourced from the Control Plane.

## Request/Response Logging

Every inference request and its response are logged to the `inference_log` table in PostgreSQL:

```sql
INSERT INTO inference_log (
    deployment_id, id, timestamp,
    input_data, output_data,
    status_code, latency_ms
) VALUES (...);
```

This logging serves two purposes:
1. **Observability:** The dashboard displays inference history, latency metrics, and error rates for each deployment.
2. **Drift Monitoring:** The stored input/output pairs enable detection of data drift over time — when the distribution of incoming inference data diverges from the training data.

## Connection Architecture

- **Single instance:** One Go process handles all inference traffic.
- **Single database pool:** The gateway maintains one PostgreSQL connection pool for logging, avoiding per-pod connection overhead.
- **Local networking:** Both the gateway and the Control Plane run on the host machine. The gateway proxies to Minikube via its exposed IP.
