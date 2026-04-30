import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { EmptyState, ErrorState, GhostButton, LabelChips, LoadingCard, PageHeader, Panel, PrimaryButton, SecondaryButton, SectionTitle, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { formatNumber } from "@/lib/utils";
import type { PlotType, RunDashboard } from "@/types/api";

const MAX_RUN_PLOTS = 4;

export function RunDetailPage() {
  const { slug = "", runNumber = "0" } = useParams();
  const runNumberValue = Number(runNumber);
  const queryClient = useQueryClient();
  const runDetailQueryKey = ["run-detail", slug, runNumberValue] as const;
  const [editingPlotId, setEditingPlotId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [plotType, setPlotType] = useState<PlotType>("line");
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([]);
  const [formError, setFormError] = useState("");

  const runQuery = useQuery({
    queryKey: runDetailQueryKey,
    queryFn: async () => {
      const [run, metrics, dashboards] = await Promise.all([
        api.getRun(slug, runNumberValue),
        api.getExperimentMetrics(slug),
        api.listRunDashboards(slug, runNumberValue),
      ]);
      return { run, metrics: metrics.metrics, dashboards };
    },
  });

  const createMutation = useMutation({
    mutationFn: (payload: { title: string; plot_type: PlotType; metrics: string[] }) =>
      api.createRunDashboard(slug, runNumberValue, payload),
    onSuccess: async (createdDashboard) => {
      queryClient.setQueryData(runDetailQueryKey, (current: typeof runQuery.data) =>
        current
          ? {
            ...current,
            dashboards: [...current.dashboards, createdDashboard].sort((left, right) => left.display_order - right.display_order),
          }
          : current,
      );
      resetForm();
      await queryClient.invalidateQueries({ queryKey: runDetailQueryKey });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ dashboardId, payload }: { dashboardId: string; payload: Partial<{ title: string; plot_type: PlotType; metrics: string[]; display_order: number }> }) =>
      api.updateRunDashboard(slug, runNumberValue, dashboardId, payload),
    onSuccess: async (updatedDashboard) => {
      queryClient.setQueryData(runDetailQueryKey, (current: typeof runQuery.data) =>
        current
          ? {
            ...current,
            dashboards: current.dashboards
              .map((dashboard) => (dashboard.id === updatedDashboard.id ? updatedDashboard : dashboard))
              .sort((left, right) => left.display_order - right.display_order),
          }
          : current,
      );
      resetForm();
      await queryClient.invalidateQueries({ queryKey: runDetailQueryKey });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (dashboardId: string) => api.deleteRunDashboard(slug, runNumberValue, dashboardId),
    onSuccess: async (_, dashboardId) => {
      queryClient.setQueryData(runDetailQueryKey, (current: typeof runQuery.data) =>
        current
          ? {
            ...current,
            dashboards: current.dashboards.filter((dashboard) => dashboard.id !== dashboardId),
          }
          : current,
      );
      if (editingPlotId) {
        resetForm();
      }
      await queryClient.invalidateQueries({ queryKey: runDetailQueryKey });
    },
  });

  const dashboards = runQuery.data?.dashboards ?? [];
  const metrics = runQuery.data?.metrics ?? [];
  const busy = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending;
  const plotLimitReached = dashboards.length >= MAX_RUN_PLOTS;

  const editingPlot = useMemo(
    () => dashboards.find((dashboard) => dashboard.id === editingPlotId) ?? null,
    [dashboards, editingPlotId],
  );

  useEffect(() => {
    if (plotType === "stat" && selectedMetrics.length > 1) {
      setSelectedMetrics(selectedMetrics.slice(0, 1));
    }
  }, [plotType, selectedMetrics]);

  if (runQuery.isLoading) {
    return <LoadingCard label="Loading run" />;
  }

  if (runQuery.isError) {
    return <ErrorState description="The requested run could not be loaded." />;
  }

  if (!runQuery.data) {
    return null;
  }

  const { run } = runQuery.data;

  function resetForm() {
    setEditingPlotId(null);
    setTitle("");
    setPlotType("line");
    setSelectedMetrics([]);
    setFormError("");
  }

  function beginEdit(dashboard: RunDashboard) {
    setEditingPlotId(dashboard.id);
    setTitle(dashboard.title);
    setPlotType(dashboard.plot_type);
    setSelectedMetrics(dashboard.metrics);
    setFormError("");
  }

  function toggleMetric(metric: string) {
    setSelectedMetrics((current) => {
      if (plotType === "stat") {
        return current[0] === metric ? [] : [metric];
      }
      return current.includes(metric) ? current.filter((item) => item !== metric) : [...current, metric];
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const trimmedTitle = title.trim();

    if (!trimmedTitle) {
      setFormError("Choose a title for this plot.");
      return;
    }
    if (selectedMetrics.length === 0) {
      setFormError("Select at least one metric.");
      return;
    }
    if (plotType === "stat" && selectedMetrics.length !== 1) {
      setFormError("Stat plots must contain exactly one metric.");
      return;
    }

    try {
      if (editingPlot) {
        await updateMutation.mutateAsync({
          dashboardId: editingPlot.id,
          payload: { title: trimmedTitle, plot_type: plotType, metrics: selectedMetrics },
        });
      } else {
        await createMutation.mutateAsync({ title: trimmedTitle, plot_type: plotType, metrics: selectedMetrics });
      }
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : "The plot could not be saved.");
    }
  }

  async function movePlot(dashboard: RunDashboard, direction: -1 | 1) {
    const nextOrder = dashboard.display_order + direction;
    if (nextOrder < 0 || nextOrder >= dashboards.length) {
      return;
    }
    await updateMutation.mutateAsync({
      dashboardId: dashboard.id,
      payload: { display_order: nextOrder },
    });
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Run"
        title={`Run ${run.run_number}`}
        description={`Experiment ${run.experiment_slug}. Started ${formatDateTime(run.created_at)}.`}
      />

      <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)] 2xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="self-start space-y-5 xl:sticky xl:top-6">
          <Panel className="space-y-5">
            <SectionTitle title="Run overview" description="Status, lifecycle, and the references attached to this execution." />

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Status</p>
              <StatusBadge status={run.status} />
              <p className="text-sm text-stone-600">
                {run.ended_at ? `Ended ${formatDateTime(run.ended_at)}` : "Still active according to the control plane."}
              </p>
            </div>

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Linked resources</p>
              <div className="space-y-4">
                <ResourceRow
                  accessibleLabel="Attached dataset"
                  detail={run.dataset ? `Version ${run.dataset.version}` : "No dataset linked"}
                  href={run.dataset ? `/datasets/${run.dataset.dataset_slug}/versions/${run.dataset.version}` : null}
                  label="Dataset"
                  name={run.dataset?.dataset_slug ?? "No dataset linked"}
                />
                <ResourceRow
                  accessibleLabel="Produced model"
                  detail={run.model ? `Version ${run.model.version}` : "No model linked"}
                  href={run.model ? `/repositories/${run.model.repository_slug}/models/${run.model.version}` : null}
                  label="Model"
                  name={run.model?.repository_slug ?? "No model linked"}
                />
              </div>
            </div>

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Labels</p>
              <LabelChips labels={run.labels} />
            </div>

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Latest metrics</p>
              {Object.entries(run.latest_metrics).length === 0 ? (
                <p className="text-sm text-stone-500">No metrics have been logged for this run yet.</p>
              ) : (
                <div className="space-y-2">
                  {(Object.entries(run.latest_metrics) as Array<[string, number]>).map(([metric, value]) => (
                    <div key={metric} className="flex items-center justify-between rounded-2xl border border-border bg-paper px-4 py-3">
                      <span className="text-sm text-stone-600">{metric}</span>
                      <span className="font-mono text-base">{formatNumber(value)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Panel>
        </aside>

        <div className="min-w-0 space-y-6">
          <Panel className="space-y-5">
            <SectionTitle
              title="Manage plots"
              description={`Saved observability panels live here. ${dashboards.length}/${MAX_RUN_PLOTS} slots used for this run.`}
            />

            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_220px]">
                <label className="space-y-2">
                  <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Plot title</span>
                  <input
                    className="w-full rounded-2xl border border-border bg-paper px-4 py-3 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Training loss"
                    value={title}
                  />
                </label>

                <div className="space-y-2">
                  <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Plot type</span>
                  <div className="grid grid-cols-2 gap-2 rounded-[24px] border border-border bg-paper p-1.5">
                    {[
                      { value: "line" as const, label: "Line chart" },
                      { value: "stat" as const, label: "Latest stat" },
                    ].map((option) => {
                      const active = plotType === option.value;
                      return (
                        <button
                          key={option.value}
                          aria-pressed={active}
                          className={`rounded-[18px] px-3 py-3 text-sm font-semibold transition ${active ? "bg-white text-ink shadow-sm" : "text-stone-600 hover:bg-white/70 hover:text-ink"
                            }`}
                          onClick={() => setPlotType(option.value)}
                          type="button"
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Metrics</p>
                  <p className="text-sm text-stone-600">
                    {plotType === "stat" ? "Pick exactly one metric." : "Pick one or more metrics."}
                  </p>
                </div>
                {metrics.length === 0 ? (
                  <p className="text-sm text-stone-500">This experiment exposes no plot-ready metrics.</p>
                ) : (
                  <div className="grid max-h-64 gap-2 overflow-y-auto pr-1 sm:grid-cols-2 xl:grid-cols-3">
                    {metrics.map((metric) => {
                      const checked = selectedMetrics.includes(metric);
                      return (
                        <button
                          aria-pressed={checked}
                          key={metric}
                          className={`flex items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm transition ${checked
                            ? "border-accent/60 bg-accent/10 text-ink"
                            : "border-border bg-paper text-stone-700 hover:border-accent/35 hover:bg-white/80"
                            }`}
                          onClick={() => toggleMetric(metric)}
                          type="button"
                        >
                          <span className="truncate pr-3">{metric}</span>
                          <span
                            className={`inline-flex h-6 min-w-6 items-center justify-center rounded-full px-2 font-mono text-[10px] ${checked ? "bg-accent text-white" : "bg-sand text-stone-500"
                              }`}
                          >
                            {checked ? "On" : plotType === "stat" ? "Pick" : "Add"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {formError ? <p className="text-sm text-danger">{formError}</p> : null}

              <div className="flex flex-wrap items-center gap-3">
                <PrimaryButton disabled={busy || (!editingPlot && plotLimitReached)} type="submit">
                  {editingPlot ? "Update plot" : "Create plot"}
                </PrimaryButton>
                {editingPlot ? (
                  <SecondaryButton disabled={busy} onClick={resetForm} type="button">
                    Cancel edit
                  </SecondaryButton>
                ) : null}
                {!editingPlot && plotLimitReached ? (
                  <p className="text-sm text-warning">This run already uses all four saved plot slots.</p>
                ) : null}
              </div>
            </form>
          </Panel>

          <div className="space-y-4">
            <SectionTitle title="Saved plots" description="Grafana-backed panels take the full width, while metadata stays tucked into the left rail." />
            {dashboards.length === 0 ? (
              <EmptyState title="No saved plots yet" description="Create up to four run plots and they will stay pinned to this run for future inspection." />
            ) : (
              <div className="space-y-4">
                {dashboards.map((dashboard, index) => (
                  <Panel key={dashboard.id} className="space-y-4 overflow-hidden">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-2xl font-semibold tracking-[-0.03em]">{dashboard.title}</h3>
                          <span className="rounded-full border border-border bg-paper px-3 py-1 font-mono text-[11px] uppercase tracking-[0.18em] text-stone-600">
                            {dashboard.plot_type}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {dashboard.metrics.map((metric) => (
                            <span key={metric} className="rounded-full border border-border bg-paper px-3 py-1 font-mono text-[11px] text-stone-700">
                              {metric}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <GhostButton disabled={busy || index === 0} onClick={() => void movePlot(dashboard, -1)} type="button">
                          Move up
                        </GhostButton>
                        <GhostButton disabled={busy || index === dashboards.length - 1} onClick={() => void movePlot(dashboard, 1)} type="button">
                          Move down
                        </GhostButton>
                        <SecondaryButton disabled={busy} onClick={() => beginEdit(dashboard)} type="button">
                          Edit
                        </SecondaryButton>
                        <SecondaryButton
                          className="border-danger/30 text-danger hover:border-danger hover:text-danger"
                          disabled={busy}
                          onClick={() => void deleteMutation.mutateAsync(dashboard.id)}
                          type="button"
                        >
                          Delete
                        </SecondaryButton>
                      </div>
                    </div>

                    <div className="rounded-[24px] border border-border bg-white/70 p-3">
                      <iframe
                        key={buildDashboardFrameRevision(dashboard)}
                        className="h-[340px] w-full rounded-[18px] border-0 bg-paper"
                        loading="lazy"
                        src={buildDashboardFrameRevision(dashboard)}
                        title={dashboard.title}
                      />
                    </div>
                  </Panel>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function buildDashboardFrameRevision(dashboard: RunDashboard) {
  const url = new URL(dashboard.iframe_url, window.location.origin);
  url.searchParams.set("rev", `${dashboard.title}:${dashboard.plot_type}:${dashboard.metrics.join(",")}:${dashboard.display_order}`);
  return url.toString();
}

function ResourceRow({
  accessibleLabel,
  label,
  name,
  detail,
  href,
}: {
  accessibleLabel: string;
  label: string;
  name: string;
  detail: string;
  href: string | null;
}) {
  const content = (
    <div className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-paper px-4 py-3 transition hover:border-accent/40">
      <div className="min-w-0">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-stone-500">{label}</p>
        <p className="mt-1 truncate text-sm font-semibold text-stone-700">{name}</p>
        <p className="text-sm text-stone-500">{detail}</p>
      </div>
      <span className="shrink-0 rounded-full bg-white px-3 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-stone-500">
        {href ? "Open" : "Missing"}
      </span>
    </div>
  );

  if (!href) {
    return content;
  }

  return (
    <Link aria-label={`${accessibleLabel}: ${name}. ${detail}`} className="block" to={href}>
      {content}
    </Link>
  );
}
