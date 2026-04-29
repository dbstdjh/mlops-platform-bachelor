# Observability & Grafana Integration

The platform provides extensive observability for both training runs (Experiment Tracking) and active deployments (Model Serving). Instead of building a custom plotting engine, the platform heavily embeds Grafana.

## Grafana Embedding Secrets
To make Grafana iframes look like native components within the React + Tailwind CSS dashboard, specific URL modifications are applied dynamically:
1. **`/d-solo/`:** Changes the route from the standard dashboard (`/d/`) to a solo panel, disabling the grid system and perfectly scaling a single chart to the iframe.
2. **`&kiosk`:** Strips away the Grafana sidebar, top navigation, time picker, and title—removing all external branding.
3. **`&theme=`:** Forces Grafana to match the platform's UI state (e.g., `&theme=dark` or `&theme=light`).

## The Plotting Resource Pipeline
Experiment-level comparison remains lightweight and frontend-driven.
- The React app uses **Recharts** for explicit run comparison on experiment pages.
- The backend serves simple JSON arrays (`[{step: 1, val: 0.9}]`) for per-run metric reads.
- The frontend requests only the selected runs and metric, capped to a small comparison set so experiment pages stay readable even when an experiment has many runs.

When complex plotting is required, the frontend remains completely dumb. If the UI needs a dropdown of features to plot, it asks the backend (`GET /repositories/{repository_slug}/models/{version}:plot_features`). FastAPI parses the model's JSON schema, extracts purely numeric keys, and returns a simple list for the frontend to render.

## Dynamic Dashboard Generation (Grafana API)
For complex, persisted observability (saved run plots today, deployment drift metrics later), the FastAPI backend acts as an orchestrator, bridging the platform's database with Grafana's Provisioning API.

The system utilizes a **Resource-Oriented Architecture** for its routing (e.g., `/runs/{run_id}/dashboards`).

### Saved Run Plots
- Each run can own up to **4** saved plots.
- Saved plots are persisted in PostgreSQL and linked through the `dashboard` / `run_dashboard` tables.
- V1 supports two plot types:
  - `line`: one or more run metrics rendered together
  - `stat`: a latest-value summary for exactly one metric
- The dashboard UI manages these plots through:
  - `GET /experiments/{experiment_slug}/runs/{run_number}/dashboards`
  - `POST /experiments/{experiment_slug}/runs/{run_number}/dashboards`
  - `PATCH /experiments/{experiment_slug}/runs/{run_number}/dashboards/{dashboard_id}`
  - `DELETE /experiments/{experiment_slug}/runs/{run_number}/dashboards/{dashboard_id}`

### The 5-Phase Provisioning Workflow
1. **Tenancy & Context Resolution:** FastAPI identifies the tenant, looks up their dedicated Grafana Folder UID (for RBAC isolation), and extracts the `run_id` or `deployment_id` to constrain the query.
2. **Dynamic JSON Generation:** The backend builds Grafana panel JSON from a small saved config (`plot_type`, selected metrics, run context) and maps it to SQL queries over `run_step`.
3. **The Provisioning API:** FastAPI sends a `POST` request to Grafana's `/api/dashboards/db` endpoint, utilizing a master Service Account Token. The payload includes the generated JSON, the `folderUid`, and `overwrite: false`.
4. **Local State Persistence (Distributed Transaction):** FastAPI opens a Postgres transaction to store the new dashboard's internal UUID, resource ID, and the returned `grafana_uid`. **Crucial:** If the Postgres commit fails, a compensating `DELETE` request is instantly sent to Grafana to prevent orphaned dashboards.
5. **Handoff to React:** FastAPI returns the generated `iframe` URL utilizing the `/d-solo/` structure to the frontend.
