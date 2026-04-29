import { API_BASE_URL } from "@/lib/constants";
import { readToken } from "@/lib/auth-storage";
import type {
  AccessTokenResponse,
  ApiKey,
  Dataset,
  DownloadResponse,
  Experiment,
  ExperimentMetricPlot,
  ExperimentMetricsResponse,
  IssuedApiKey,
  Model,
  Repository,
  Run,
  RunDashboard,
  RunMetricPlot,
  User,
} from "@/types/api";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit, withAuth = true): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");

  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (withAuth) {
    const token = readToken();
    if (!token) {
      throw new ApiError(401, "Authentication required");
    }
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const detail = await parseError(response);
    if (response.status === 401) {
      unauthorizedHandler?.();
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  register: (payload: { email: string; password: string }) =>
    apiFetch<User>("/users:register", { method: "POST", body: JSON.stringify(payload) }, false),
  login: (payload: { email: string; password: string }) =>
    apiFetch<AccessTokenResponse>("/users:login", { method: "POST", body: JSON.stringify(payload) }, false),
  getMe: () => apiFetch<User>("/users/me"),
  listApiKeys: () => apiFetch<ApiKey[]>("/users/me/api-keys"),
  createApiKey: (payload: { name: string }) =>
    apiFetch<IssuedApiKey>("/users/me/api-keys", { method: "POST", body: JSON.stringify(payload) }),
  revokeApiKey: (name: string) =>
    apiFetch<{ status: string }>(`/users/me/api-keys/${name}:revoke`, { method: "POST" }),
  listExperiments: () => apiFetch<Experiment[]>("/experiments"),
  getExperiment: (slug: string) => apiFetch<Experiment>(`/experiments/${slug}`),
  listRuns: (slug: string) => apiFetch<Run[]>(`/experiments/${slug}/runs`),
  getRun: (slug: string, runNumber: number) => apiFetch<Run>(`/experiments/${slug}/runs/${runNumber}`),
  getExperimentMetrics: (slug: string) => apiFetch<ExperimentMetricsResponse>(`/experiments/${slug}/metrics`),
  getExperimentMetricPlot: (slug: string, metricName: string) =>
    apiFetch<ExperimentMetricPlot>(`/experiments/${slug}/plots/${metricName}`),
  getRunMetricPlot: (slug: string, runNumber: number, metricName: string) =>
    apiFetch<RunMetricPlot>(`/experiments/${slug}/runs/${runNumber}/plots/${metricName}`),
  listRunDashboards: (slug: string, runNumber: number) =>
    apiFetch<RunDashboard[]>(`/experiments/${slug}/runs/${runNumber}/dashboards`),
  createRunDashboard: (
    slug: string,
    runNumber: number,
    payload: { title: string; plot_type: "line" | "stat"; metrics: string[] },
  ) => apiFetch<RunDashboard>(`/experiments/${slug}/runs/${runNumber}/dashboards`, { method: "POST", body: JSON.stringify(payload) }),
  updateRunDashboard: (
    slug: string,
    runNumber: number,
    dashboardId: string,
    payload: Partial<{ title: string; plot_type: "line" | "stat"; metrics: string[]; display_order: number }>,
  ) =>
    apiFetch<RunDashboard>(
      `/experiments/${slug}/runs/${runNumber}/dashboards/${dashboardId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  deleteRunDashboard: (slug: string, runNumber: number, dashboardId: string) =>
    apiFetch<void>(`/experiments/${slug}/runs/${runNumber}/dashboards/${dashboardId}`, { method: "DELETE" }),
  listDatasets: () => apiFetch<Dataset[]>("/datasets"),
  getDataset: (slug: string, version: number) => apiFetch<Dataset>(`/datasets/${slug}/versions/${version}`),
  getDatasetDownload: (slug: string, version?: number) =>
    version == null
      ? apiFetch<DownloadResponse>(`/datasets/${slug}:download`)
      : apiFetch<DownloadResponse>(`/datasets/${slug}/versions/${version}:download`),
  listRepositories: () => apiFetch<Repository[]>("/repositories"),
  getRepository: (slug: string) => apiFetch<Repository>(`/repositories/${slug}`),
  listModels: (slug: string) => apiFetch<Model[]>(`/repositories/${slug}/models`),
  getModel: (slug: string, version: string) => apiFetch<Model>(`/repositories/${slug}/models/${version}`),
  getModelDownload: (slug: string, version: string) =>
    apiFetch<DownloadResponse>(`/repositories/${slug}/models/${version}:download`),
};
