import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorState, LabelChips, LoadingCard, PageHeader, Panel, PrimaryButton, SecondaryButton, SectionTitle, SelectInput, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import type { DeploymentDashboard, DeploymentPlotSource, DeploymentPlotType } from "@/types/api";

export function DeploymentDetailPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const deploymentStatusKey = ["deployment-status", slug] as const;
  const deploymentDashboardsKey = ["deployment-dashboards", slug] as const;
  const deploymentFieldsKey = ["deployment-plot-fields", slug] as const;
  const [title, setTitle] = useState("");
  const [plotType, setPlotType] = useState<DeploymentPlotType>("time_series");
  const [source, setSource] = useState<DeploymentPlotSource>("input");
  const [fieldPath, setFieldPath] = useState("");
  const [formError, setFormError] = useState("");
  const [timeRange, setTimeRange] = useState("now-15m");
  const [frameRevision, setFrameRevision] = useState(0);
  const [schemasOpen, setSchemasOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<null | {
    title: string;
    description: string;
    confirmLabel: string;
    tone: "warning" | "danger";
    onConfirm: () => void;
  }>(null);

  const deploymentQuery = useQuery({
    queryKey: deploymentStatusKey,
    queryFn: () => api.getDeployment(slug),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && isDeploymentInProgress(data.status) ? 1000 : false;
    },
  });

  const dashboardsQuery = useQuery({
    queryKey: deploymentDashboardsKey,
    queryFn: () => api.listDeploymentDashboards(slug),
  });

  const fieldsQuery = useQuery({
    queryKey: deploymentFieldsKey,
    queryFn: () => api.listDeploymentPlotFields(slug),
  });

  const createDashboardMutation = useMutation({
    mutationFn: (payload: { title: string; plot_type: DeploymentPlotType; source: DeploymentPlotSource; field_path: string }) =>
      api.createDeploymentDashboard(slug, payload),
    onSuccess: async (dashboard) => {
      queryClient.setQueryData(deploymentDashboardsKey, (current: typeof dashboardsQuery.data) =>
        current ? [...current, dashboard] : current,
      );
      setTitle("");
      setFieldPath("");
      setFormError("");
      await queryClient.invalidateQueries({ queryKey: deploymentDashboardsKey });
    },
  });

  const deleteDashboardMutation = useMutation({
    mutationFn: (dashboardId: string) => api.deleteDeploymentDashboard(slug, dashboardId),
    onSuccess: async (_, dashboardId) => {
      queryClient.setQueryData(deploymentDashboardsKey, (current: typeof dashboardsQuery.data) =>
        current ? current.filter((dashboard) => dashboard.id !== dashboardId) : current,
      );
      await queryClient.invalidateQueries({ queryKey: deploymentDashboardsKey });
    },
  });

  const deleteDeploymentMutation = useMutation({
    mutationFn: () => api.deleteDeployment(slug),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["deployments"] });
      await queryClient.invalidateQueries({ queryKey: deploymentStatusKey });
      navigate("/deployments");
    },
  });

  const purgeDeploymentMutation = useMutation({
    mutationFn: () => api.purgeDeployment(slug),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["deployments"] });
      navigate("/deployments");
    },
  });

  const fields = fieldsQuery.data ?? [];
  const availableFields = useMemo(() => fields.filter((field) => field.source === source), [fields, source]);
  const selectedField = useMemo(
    () => availableFields.find((field) => field.path === fieldPath) ?? null,
    [availableFields, fieldPath],
  );
  const availablePlotTypes = selectedField?.plot_types ?? DEFAULT_PLOT_TYPES;

  useEffect(() => {
    if (selectedField && !selectedField.plot_types.includes(plotType)) {
      setPlotType(selectedField.plot_types[0] ?? "distribution");
    }
  }, [plotType, selectedField]);

  if (deploymentQuery.isLoading || dashboardsQuery.isLoading || fieldsQuery.isLoading) {
    return <LoadingCard label="Loading deployment" />;
  }

  if (deploymentQuery.isError || dashboardsQuery.isError || fieldsQuery.isError) {
    return <ErrorState description="The requested deployment could not be loaded." />;
  }

  if (!deploymentQuery.data || !dashboardsQuery.data || !fieldsQuery.data) {
    return null;
  }

  const deployment = deploymentQuery.data;
  const dashboards = dashboardsQuery.data;

  async function handleCreateDashboard(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setFormError("Choose a plot title.");
      return;
    }
    if (!fieldPath) {
      setFormError("Choose a plot-ready input or output field.");
      return;
    }

    try {
      await createDashboardMutation.mutateAsync({
        title: trimmedTitle,
        plot_type: plotType,
        source,
        field_path: fieldPath,
      });
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : "The plot could not be created.");
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Deployment"
        title={deployment.name}
        description={`Serving endpoint ${deployment.slug}. Created ${formatDateTime(deployment.created_at)}.`}
        action={
          <div className="flex flex-wrap gap-2">
            <SecondaryButton
              className="border-warning/30 text-warning hover:border-warning hover:text-warning"
              disabled={deleteDeploymentMutation.isPending || purgeDeploymentMutation.isPending}
              onClick={() =>
                setConfirmation({
                  title: "Undeploy endpoint",
                  description: "This will enqueue Kubernetes resource deletion and stop serving traffic for this deployment.",
                  confirmLabel: "Undeploy",
                  tone: "warning",
                  onConfirm: () => deleteDeploymentMutation.mutate(),
                })
              }
              type="button"
            >
              {deleteDeploymentMutation.isPending ? "Undeploying..." : "Undeploy"}
            </SecondaryButton>
            <SecondaryButton
              className="border-danger/30 text-danger hover:border-danger hover:text-danger"
              disabled={deleteDeploymentMutation.isPending || purgeDeploymentMutation.isPending}
              onClick={() =>
                setConfirmation({
                  title: "Delete deployment record",
                  description: "This permanently removes the control-plane record and its saved deployment observability metadata.",
                  confirmLabel: "Delete record",
                  tone: "danger",
                  onConfirm: () => purgeDeploymentMutation.mutate(),
                })
              }
              type="button"
            >
              {purgeDeploymentMutation.isPending ? "Deleting..." : "Delete record"}
            </SecondaryButton>
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)] 2xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="self-start space-y-5 xl:sticky xl:top-6">
          <Panel className="space-y-5">
            <SectionTitle title="Overview" description="Status, source, endpoint, and resource metadata." />

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Status</p>
              <StatusBadge status={deployment.status} />
            </div>

            <div className="grid gap-3">
              <Meta label="Slug">{deployment.slug}</Meta>
              <Meta label="Source">{deployment.source_type === "image" ? "Custom image" : "Model artifact"}</Meta>
              <Meta label="Endpoint">{deployment.endpoint_url ?? "Pending"}</Meta>
              <Meta label="Image">{deployment.image_ref ?? "File-backed deployment"}</Meta>
            </div>

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Labels</p>
              <LabelChips labels={deployment.labels} />
            </div>

            <div className="flex flex-wrap gap-3">
              <SecondaryButton onClick={() => setSchemasOpen(true)} type="button">
                View schemas
              </SecondaryButton>
              <Link className="inline-flex items-center text-sm font-semibold text-accent" to="/deployments">
                Back to deployments
              </Link>
            </div>
          </Panel>
        </aside>

        <div className="min-w-0 space-y-6">
          <Panel className="space-y-5">
            <SectionTitle title="Create custom plot" description="Build Grafana panels from plot-ready fields in the deployment input or output schema." />
            <form className="space-y-4" onSubmit={handleCreateDashboard}>
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px_220px]">
                <label className="space-y-2">
                  <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Plot title</span>
                  <input
                    className="w-full rounded-2xl border border-border bg-paper px-4 py-3 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Prediction score distribution"
                    value={title}
                  />
                </label>

                <label className="space-y-2">
                  <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Source</span>
                  <SelectInput
                    ariaLabel="Source"
                    onValueChange={(value) => {
                      setSource(value as DeploymentPlotSource);
                      setFieldPath("");
                    }}
                    options={[
                      { value: "input", label: "Input" },
                      { value: "output", label: "Output" },
                    ]}
                    value={source}
                  />
                </label>

                <label className="space-y-2">
                  <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Plot type</span>
                  <SelectInput
                    ariaLabel="Plot type"
                    onValueChange={(value) => setPlotType(value as DeploymentPlotType)}
                    options={availablePlotTypes.map((type) => ({ value: type, label: PLOT_TYPE_LABELS[type] }))}
                    value={plotType}
                  />
                </label>
              </div>

              <label className="space-y-2 block">
                <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Field</span>
                <SelectInput
                  ariaLabel="Field"
                  disabled={availableFields.length === 0}
                  onValueChange={setFieldPath}
                  options={[
                    { value: "", label: "Choose a plot-ready field" },
                    ...availableFields.map((field) => ({
                      value: field.path,
                      label: `${field.path} [${FIELD_TYPE_LABELS[field.value_type]}]`,
                    })),
                  ]}
                  value={fieldPath}
                  placeholder="Choose a plot-ready field"
                />
              </label>

              {selectedField ? (
                <div className="flex flex-wrap gap-2">
                  <Chip>{FIELD_TYPE_LABELS[selectedField.value_type]}</Chip>
                  {selectedField.plot_types.map((type) => (
                    <Chip key={type}>{PLOT_TYPE_LABELS[type]}</Chip>
                  ))}
                </div>
              ) : null}

              {availableFields.length === 0 ? (
                <p className="text-sm text-stone-500">No plot-ready {source} fields were found in this deployment schema.</p>
              ) : null}
              {formError ? <p className="text-sm text-danger">{formError}</p> : null}

              <PrimaryButton disabled={createDashboardMutation.isPending || availableFields.length === 0} type="submit">
                {createDashboardMutation.isPending ? "Creating..." : "Create plot"}
              </PrimaryButton>
            </form>
          </Panel>

          <div className="space-y-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <SectionTitle title="Observability" description="Latency and status code panels are created by default. Custom panels stay with this deployment." />
              <div className="flex flex-wrap items-center justify-end gap-2 sm:flex-nowrap">
                <SelectInput
                  aria-label="Observability time range"
                  className="w-[160px]"
                  onValueChange={(value) => {
                    setTimeRange(value);
                    setFrameRevision((current) => current + 1);
                  }}
                  options={TIME_RANGES}
                  value={timeRange}
                />
                <SecondaryButton
                  className="h-10 min-w-[118px] whitespace-nowrap px-4 py-0"
                  onClick={() => {
                    void queryClient.invalidateQueries({ queryKey: deploymentDashboardsKey });
                    setFrameRevision((current) => current + 1);
                  }}
                  type="button"
                >
                  Refresh plots
                </SecondaryButton>
              </div>
            </div>
            {dashboards.length === 0 ? (
              <Panel>
                <p className="text-sm text-stone-500">No observability panels have been provisioned yet.</p>
              </Panel>
            ) : (
              <div className="grid gap-5 xl:grid-cols-2">
                {dashboards.map((dashboard) => (
                  <DeploymentDashboardPanel
                    dashboard={dashboard}
                    key={dashboard.id}
                    frameRevision={frameRevision}
                    timeRange={timeRange}
                    onDelete={(dashboardId) =>
                      setConfirmation({
                        title: "Delete custom plot",
                        description: "This removes the saved Grafana panel from this deployment.",
                        confirmLabel: "Delete plot",
                        tone: "danger",
                        onConfirm: () => deleteDashboardMutation.mutate(dashboardId),
                      })
                    }
                    busy={deleteDashboardMutation.isPending}
                  />
                ))}
              </div>
            )}
          </div>

        </div>
      </div>
      {schemasOpen ? (
        <SchemaDialog
          inputSchema={deployment.input_schema}
          outputSchema={deployment.output_schema}
          onClose={() => setSchemasOpen(false)}
        />
      ) : null}
      {confirmation ? (
        <ConfirmDialog
          title={confirmation.title}
          description={confirmation.description}
          confirmLabel={confirmation.confirmLabel}
          tone={confirmation.tone}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => {
            confirmation.onConfirm();
            setConfirmation(null);
          }}
        />
      ) : null}
    </div>
  );
}

function DeploymentDashboardPanel({
  dashboard,
  busy,
  frameRevision,
  timeRange,
  onDelete,
}: {
  dashboard: DeploymentDashboard;
  busy: boolean;
  frameRevision: number;
  timeRange: string;
  onDelete: (dashboardId: string) => void;
}) {
  return (
    <Panel className="space-y-4 overflow-hidden">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <h3 className="truncate text-xl font-semibold tracking-[-0.03em]">{dashboard.title}</h3>
          <div className="flex flex-wrap gap-2">
            <Chip>{dashboard.plot_type}</Chip>
            <Chip>{dashboard.source}</Chip>
            {dashboard.field_path ? <Chip>{dashboard.field_path}</Chip> : null}
            {dashboard.is_system_locked ? <Chip>system</Chip> : null}
          </div>
        </div>
        {!dashboard.is_system_locked ? (
          <SecondaryButton
            className="border-danger/30 text-danger hover:border-danger hover:text-danger"
            disabled={busy}
            onClick={() => onDelete(dashboard.id)}
            type="button"
          >
            Delete
          </SecondaryButton>
        ) : null}
      </div>

      <div className="rounded-[20px] border border-border bg-white/70 p-3">
        <iframe
          className="h-[320px] w-full rounded-2xl border-0 bg-paper"
          loading="lazy"
          key={buildDashboardFrameRevision(dashboard, frameRevision, timeRange)}
          src={buildDashboardFrameRevision(dashboard, frameRevision, timeRange)}
          title={dashboard.title}
        />
      </div>
    </Panel>
  );
}

function SchemaDialog({
  inputSchema,
  outputSchema,
  onClose,
}: {
  inputSchema: Record<string, unknown> | null;
  outputSchema: Record<string, unknown> | null;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-4 py-6 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Deployment schemas"
    >
      <div
        className="max-h-[88vh] w-full max-w-6xl overflow-hidden rounded-[28px] border border-border bg-mist shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 border-b border-border bg-paper px-6 py-4">
          <SectionTitle title="Schemas" description="Input and output contracts for this deployment." />
          <SecondaryButton onClick={onClose} type="button">
            Close
          </SecondaryButton>
        </div>
        <div className="grid max-h-[calc(88vh-88px)] gap-5 overflow-auto p-6 xl:grid-cols-2">
          <SchemaPanel title="Input schema" schema={inputSchema} />
          <SchemaPanel title="Output schema" schema={outputSchema} />
        </div>
      </div>
    </div>
  );
}

function SchemaPanel({ title, schema }: { title: string; schema: Record<string, unknown> | null }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const resetTimer = useRef<number | null>(null);
  const schemaText = JSON.stringify(schema ?? {}, null, 2);

  useEffect(() => {
    return () => {
      if (resetTimer.current !== null) {
        window.clearTimeout(resetTimer.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    if (resetTimer.current !== null) {
      window.clearTimeout(resetTimer.current);
    }

    try {
      await copyTextToClipboard(schemaText);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }

    resetTimer.current = window.setTimeout(() => setCopyState("idle"), 1600);
  };

  return (
    <Panel className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <SectionTitle title={title} />
        <SecondaryButton onClick={handleCopy} type="button">
          {copyState === "copied" ? "Copied" : copyState === "failed" ? "Failed" : "Copy"}
        </SecondaryButton>
      </div>
      <pre className="max-h-96 overflow-auto rounded-2xl border border-border bg-ink p-4 text-xs text-paper">
        {schemaText}
      </pre>
    </Panel>
  );
}

async function copyTextToClipboard(text: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to the textarea path for HTTP and permission-denied cases.
    }
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  textArea.style.top = "0";

  const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const selection = document.getSelection();
  const selectedRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  const copied = typeof document.execCommand === "function" && document.execCommand("copy");
  document.body.removeChild(textArea);

  if (selectedRange && selection) {
    selection.removeAllRanges();
    selection.addRange(selectedRange);
  }
  activeElement?.focus();

  if (!copied) {
    throw new Error("Clipboard copy failed");
  }
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl border border-border bg-paper/75 p-4">
      <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{label}</p>
      <div className="mt-2 break-words text-sm text-stone-700">{children}</div>
    </div>
  );
}

function ConfirmDialog({
  title,
  description,
  confirmLabel,
  tone,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  tone: "warning" | "danger";
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const toneClass = tone === "danger" ? "border-danger/30 text-danger hover:border-danger" : "border-warning/30 text-warning hover:border-warning";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-[28px] border border-border bg-mist p-6 shadow-2xl">
        <SectionTitle title={title} description={description} />
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <SecondaryButton onClick={onCancel} type="button">
            Cancel
          </SecondaryButton>
          <SecondaryButton className={toneClass} onClick={onConfirm} type="button">
            {confirmLabel}
          </SecondaryButton>
        </div>
      </div>
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-border bg-paper px-3 py-1 font-mono text-[11px] text-stone-700">
      {children}
    </span>
  );
}

const DEFAULT_PLOT_TYPES: DeploymentPlotType[] = ["time_series", "distribution"];

const PLOT_TYPE_LABELS: Record<DeploymentPlotType, string> = {
  time_series: "Time series",
  distribution: "Distribution",
  category_time_series: "Category counts over time",
};

const FIELD_TYPE_LABELS = {
  number: "Number",
  number_array: "Number array",
  number_matrix: "Number matrix",
  number_matrix_index: "Number matrix index",
  category: "Category",
  category_array: "Category array",
  boolean: "Boolean",
  boolean_array: "Boolean array",
} as const;

const IN_PROGRESS_DEPLOYMENT_STATUSES = new Set(["PENDING", "DEPLOYING", "DELETING"]);

function isDeploymentInProgress(status: string) {
  return IN_PROGRESS_DEPLOYMENT_STATUSES.has(status);
}

const TIME_RANGES = [
  { value: "now-5m", label: "Last 5 minutes" },
  { value: "now-15m", label: "Last 15 minutes" },
  { value: "now-1h", label: "Last hour" },
  { value: "now-6h", label: "Last 6 hours" },
  { value: "now-24h", label: "Last 24 hours" },
  { value: "now-7d", label: "Last 7 days" },
];

function buildDashboardFrameRevision(dashboard: DeploymentDashboard, frameRevision: number, timeRange: string) {
  const url = new URL(dashboard.iframe_url, window.location.origin);
  url.searchParams.set("from", timeRange);
  url.searchParams.set("to", "now");
  url.searchParams.set("refresh", "30s");
  url.searchParams.set("rev", `${dashboard.title}:${dashboard.plot_type}:${dashboard.source}:${dashboard.field_path ?? ""}:${frameRevision}`);
  return url.toString();
}
