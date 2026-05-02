export type Labels = Record<string, string | number | boolean | null>;

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface ApiKey {
  name: string;
  prefix: string;
  is_revoked: boolean;
  created_at: string;
}

export interface IssuedApiKey extends ApiKey {
  api_key: string;
}

export interface ArtifactRegistryStatus {
  enabled: boolean;
  registry_host: string;
  username: string | null;
  namespace: string | null;
  docker_login_command: string | null;
}

export interface RegistryToken {
  name: string;
  token_last_eight: string | null;
  created_at: string | null;
}

export interface IssuedRegistryToken extends RegistryToken {
  token: string;
  registry_host: string;
  username: string;
  docker_login_command: string;
}

export interface ArtifactImageTag {
  tag: string;
  image_ref: string;
  created_at: string | null;
}

export interface ArtifactImage {
  name: string;
  tags: ArtifactImageTag[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  search: string | null;
  sort_by: string;
  sort_dir: "asc" | "desc";
}

export interface ListQuery {
  search?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export type DeploymentSourceType = "file" | "image";

export interface Deployment {
  name: string;
  slug: string;
  status: string;
  endpoint_url: string | null;
  input_schema: Record<string, unknown> | null;
  output_schema: Record<string, unknown> | null;
  created_at: string;
  labels: Labels;
  source_type: DeploymentSourceType;
  image_ref: string | null;
}

export type DeploymentPlotType = "time_series" | "distribution" | "category_time_series";
export type DeploymentPlotSource = "input" | "output";
export type DeploymentPlotValueType =
  | "number"
  | "number_array"
  | "number_matrix"
  | "number_matrix_index"
  | "category"
  | "category_array"
  | "boolean"
  | "boolean_array";

export interface DeploymentDashboard {
  id: string;
  title: string;
  plot_type: string;
  source: string;
  field_path: string | null;
  is_system_locked: boolean;
  iframe_url: string;
  created_at: string;
}

export interface DeploymentPlotField {
  source: DeploymentPlotSource;
  path: string;
  value_type: DeploymentPlotValueType;
  plot_types: DeploymentPlotType[];
}

export interface DatasetRef {
  dataset_slug: string;
  version: number;
}

export interface ModelRef {
  repository_slug: string;
  version: string;
}

export interface RunRef {
  experiment_slug: string;
  run_number: number;
}

export interface PlotPoint {
  step: number;
  val: number;
  timestamp: string;
}

export interface RunSummary {
  run_number: number;
  status: string;
  created_at: string;
  ended_at: string | null;
  dataset: DatasetRef | null;
  model: ModelRef | null;
  latest_metrics: Record<string, number>;
  labels: Labels;
}

export interface Run extends RunSummary {
  experiment_slug: string;
}

export interface Experiment {
  name: string;
  slug: string;
  logged_data_template: string[];
  created_at: string;
  labels: Labels;
  run_count: number;
  latest_run: RunSummary | null;
}

export interface ExperimentMetricsResponse {
  metrics: string[];
}

export interface ExperimentMetricSeries {
  run: RunRef;
  points: PlotPoint[];
}

export interface ExperimentMetricPlot {
  metric_name: string;
  series: ExperimentMetricSeries[];
}

export interface RunMetricPlot {
  metric_name: string;
  points: PlotPoint[];
}

export type PlotType = "line" | "stat";

export interface RunDashboard {
  id: string;
  title: string;
  plot_type: PlotType;
  metrics: string[];
  display_order: number;
  iframe_url: string;
  created_at: string;
}

export interface Dataset {
  name: string;
  slug: string;
  version: number;
  status: string;
  file_type: string | null;
  created_at: string;
  labels: Labels;
}

export interface DownloadResponse {
  download_url: string;
}

export interface Repository {
  name: string;
  slug: string;
  is_deleted: boolean;
  created_at: string;
  labels: Labels;
}

export interface Model {
  repository_slug: string;
  name: string;
  version: string;
  run: RunRef | null;
  is_deleted: boolean;
  s3_uri: string | null;
  status: string;
  file_type: "pickle" | "undefined";
  created_at: string;
  labels: Labels;
}

export interface OverviewSummary {
  experiment_count: number;
  dataset_count: number;
  repository_count: number;
  deployment_count: number;
}

export interface OverviewRecent {
  experiments: Experiment[];
  datasets: Dataset[];
  repositories: Repository[];
  deployments: Deployment[];
}
