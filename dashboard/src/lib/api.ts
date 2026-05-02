import { API_BASE_URL } from "@/lib/constants";
import { readToken } from "@/lib/auth-storage";
import type {
  AccessTokenResponse,
  ApiKey,
  ArtifactImage,
  ArtifactRegistryStatus,
  Dataset,
  Deployment,
  DeploymentDashboard,
  DeploymentPlotField,
  DeploymentPlotSource,
  DeploymentPlotType,
  DownloadResponse,
  Experiment,
  ExperimentMetricPlot,
  ExperimentMetricsResponse,
  IssuedApiKey,
  IssuedRegistryToken,
  ListQuery,
  Model,
  OverviewRecent,
  OverviewSummary,
  PaginatedResponse,
  RegistryToken,
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

function pathPart(value: string | number): string {
  return encodeURIComponent(String(value));
}

function listQuery(params: ListQuery = {}): string {
  const query = new URLSearchParams({ paginated: "true" });
  if (params.search?.trim()) {
    query.set("search", params.search.trim());
  }
  if (params.sort_by) {
    query.set("sort_by", params.sort_by);
  }
  if (params.sort_dir) {
    query.set("sort_dir", params.sort_dir);
  }
  if (params.limit != null) {
    query.set("limit", String(params.limit));
  }
  if (params.offset != null) {
    query.set("offset", String(params.offset));
  }
  return `?${query.toString()}`;
}

async function apiFetchPage<T>(path: string, params: ListQuery = {}): Promise<PaginatedResponse<T>> {
  const payload = await apiFetch<PaginatedResponse<T> | T[]>(`${path}${listQuery(params)}`);
  if (Array.isArray(payload)) {
    return {
      items: payload,
      total: payload.length,
      limit: params.limit ?? payload.length,
      offset: params.offset ?? 0,
      search: params.search ?? null,
      sort_by: params.sort_by ?? "created_at",
      sort_dir: params.sort_dir ?? "desc",
    };
  }
  return payload;
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
    apiFetch<{ status: string }>(`/users/me/api-keys/${pathPart(name)}:revoke`, { method: "POST" }),
  getOverviewSummary: () => apiFetch<OverviewSummary>("/overview/summary"),
  getOverviewRecent: () => apiFetch<OverviewRecent>("/overview/recent"),
  getArtifactRegistryStatus: () => apiFetch<ArtifactRegistryStatus>("/artifact-registry/status"),
  enableArtifactRegistry: () => apiFetch<ArtifactRegistryStatus>("/artifact-registry:enable", { method: "POST" }),
  listRegistryTokens: () => apiFetch<RegistryToken[]>("/artifact-registry/tokens"),
  createRegistryToken: (payload: { name: string }) =>
    apiFetch<IssuedRegistryToken>("/artifact-registry/tokens", { method: "POST", body: JSON.stringify(payload) }),
  revokeRegistryToken: (name: string) =>
    apiFetch<{ status: string }>(`/artifact-registry/tokens/${pathPart(name)}:revoke`, { method: "POST" }),
  listArtifactImages: () => apiFetch<ArtifactImage[]>("/artifact-registry/images"),
  listArtifactImagesPage: (params?: ListQuery) =>
    apiFetchPage<ArtifactImage>("/artifact-registry/images", params),
  createArtifactImageDeployment: (
    imageName: string,
    tag: string,
    payload: {
      name: string;
      input_schema?: Record<string, unknown> | null;
      output_schema?: Record<string, unknown> | null;
      labels?: Record<string, unknown>;
    },
  ) =>
    apiFetch<Deployment>(
      `/artifact-registry/images/${pathPart(imageName)}/tags/${pathPart(tag)}/deployments`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  listDeployments: () => apiFetch<Deployment[]>("/deployments"),
  listDeploymentsPage: (params?: ListQuery) =>
    apiFetchPage<Deployment>("/deployments", params),
  getDeployment: (slug: string) => apiFetch<Deployment>(`/deployments/${pathPart(slug)}`),
  deleteDeployment: (slug: string) => apiFetch<Deployment>(`/deployments/${pathPart(slug)}`, { method: "DELETE" }),
  purgeDeployment: (slug: string) => apiFetch<void>(`/deployments/${pathPart(slug)}:purge`, { method: "DELETE" }),
  createModelDeployment: (
    repositorySlug: string,
    version: string,
    payload: {
      name: string;
      input_schema?: Record<string, unknown> | null;
      output_schema?: Record<string, unknown> | null;
      labels?: Record<string, unknown>;
    },
  ) =>
    apiFetch<Deployment>(
      `/repositories/${pathPart(repositorySlug)}/models/${pathPart(version)}/deployments`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  listDeploymentDashboards: (slug: string) =>
    apiFetch<DeploymentDashboard[]>(`/deployments/${pathPart(slug)}/dashboards`),
  createDeploymentDashboard: (
    slug: string,
    payload: {
      title: string;
      plot_type: DeploymentPlotType;
      source: DeploymentPlotSource;
      field_path: string;
    },
  ) =>
    apiFetch<DeploymentDashboard>(`/deployments/${pathPart(slug)}/dashboards`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteDeploymentDashboard: (slug: string, dashboardId: string) =>
    apiFetch<void>(`/deployments/${pathPart(slug)}/dashboards/${pathPart(dashboardId)}`, { method: "DELETE" }),
  listDeploymentPlotFields: (slug: string) =>
    apiFetch<DeploymentPlotField[]>(`/deployments/${pathPart(slug)}/plot-fields`),
  listExperiments: () => apiFetch<Experiment[]>("/experiments"),
  listExperimentsPage: (params?: ListQuery) =>
    apiFetchPage<Experiment>("/experiments", params),
  getExperiment: (slug: string) => apiFetch<Experiment>(`/experiments/${pathPart(slug)}`),
  listRuns: (slug: string) => apiFetch<Run[]>(`/experiments/${pathPart(slug)}/runs`),
  listRunsPage: (slug: string, params?: ListQuery) =>
    apiFetchPage<Run>(`/experiments/${pathPart(slug)}/runs`, params),
  getRun: (slug: string, runNumber: number) => apiFetch<Run>(`/experiments/${pathPart(slug)}/runs/${pathPart(runNumber)}`),
  getExperimentMetrics: (slug: string) => apiFetch<ExperimentMetricsResponse>(`/experiments/${pathPart(slug)}/metrics`),
  getExperimentMetricPlot: (slug: string, metricName: string) =>
    apiFetch<ExperimentMetricPlot>(`/experiments/${pathPart(slug)}/plots/${pathPart(metricName)}`),
  getRunMetricPlot: (slug: string, runNumber: number, metricName: string) =>
    apiFetch<RunMetricPlot>(`/experiments/${pathPart(slug)}/runs/${pathPart(runNumber)}/plots/${pathPart(metricName)}`),
  listRunDashboards: (slug: string, runNumber: number) =>
    apiFetch<RunDashboard[]>(`/experiments/${pathPart(slug)}/runs/${pathPart(runNumber)}/dashboards`),
  createRunDashboard: (
    slug: string,
    runNumber: number,
    payload: { title: string; plot_type: "line" | "stat"; metrics: string[] },
  ) => apiFetch<RunDashboard>(`/experiments/${pathPart(slug)}/runs/${pathPart(runNumber)}/dashboards`, { method: "POST", body: JSON.stringify(payload) }),
  updateRunDashboard: (
    slug: string,
    runNumber: number,
    dashboardId: string,
    payload: Partial<{ title: string; plot_type: "line" | "stat"; metrics: string[]; display_order: number }>,
  ) =>
    apiFetch<RunDashboard>(
      `/experiments/${pathPart(slug)}/runs/${pathPart(runNumber)}/dashboards/${pathPart(dashboardId)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
  deleteRunDashboard: (slug: string, runNumber: number, dashboardId: string) =>
    apiFetch<void>(`/experiments/${pathPart(slug)}/runs/${pathPart(runNumber)}/dashboards/${pathPart(dashboardId)}`, { method: "DELETE" }),
  listDatasets: () => apiFetch<Dataset[]>("/datasets"),
  listDatasetsPage: (params?: ListQuery) =>
    apiFetchPage<Dataset>("/datasets", params),
  getDataset: (slug: string, version: number) => apiFetch<Dataset>(`/datasets/${pathPart(slug)}/versions/${pathPart(version)}`),
  getDatasetDownload: (slug: string, version?: number) =>
    version == null
      ? apiFetch<DownloadResponse>(`/datasets/${pathPart(slug)}:download`)
      : apiFetch<DownloadResponse>(`/datasets/${pathPart(slug)}/versions/${pathPart(version)}:download`),
  listRepositories: () => apiFetch<Repository[]>("/repositories"),
  listRepositoriesPage: (params?: ListQuery) =>
    apiFetchPage<Repository>("/repositories", params),
  getRepository: (slug: string) => apiFetch<Repository>(`/repositories/${pathPart(slug)}`),
  listModels: (slug: string) => apiFetch<Model[]>(`/repositories/${pathPart(slug)}/models`),
  listModelsPage: (slug: string, params?: ListQuery) =>
    apiFetchPage<Model>(`/repositories/${pathPart(slug)}/models`, params),
  getModel: (slug: string, version: string) => apiFetch<Model>(`/repositories/${pathPart(slug)}/models/${pathPart(version)}`),
  getModelDownload: (slug: string, version: string) =>
    apiFetch<DownloadResponse>(`/repositories/${pathPart(slug)}/models/${pathPart(version)}:download`),
};
