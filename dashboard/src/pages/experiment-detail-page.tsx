import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { EmptyState, ErrorState, LabelChips, LoadingCard, PageHeader, PaginationControls, Panel, SearchInput, SectionTitle, SelectInput, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { formatNumber } from "@/lib/utils";

const MAX_VISIBLE_RUN_METRICS = 4;
const PAGE_SIZE = 12;

export function ExperimentDetailPage() {
  const { slug = "" } = useParams();
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("run_number");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);

  const summaryQuery = useQuery({
    queryKey: ["experiment", slug, { search, sortBy, sortDir, offset }],
    queryFn: async () => {
      const [experiment, runs] = await Promise.all([
        api.getExperiment(slug),
        api.listRunsPage(slug, { search, sort_by: sortBy, sort_dir: sortDir, limit: PAGE_SIZE, offset }),
      ]);
      return { experiment, runs };
    },
  });

  if (summaryQuery.isLoading) {
    return <LoadingCard label="Loading experiment" />;
  }

  if (summaryQuery.isError) {
    return <ErrorState description="The experiment detail page could not be loaded." />;
  }

  if (!summaryQuery.data) {
    return null;
  }

  const { experiment, runs } = summaryQuery.data;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Experiment"
        title={experiment.name}
        description={`Slug ${experiment.slug}. Created ${formatDateTime(experiment.created_at)} with ${experiment.run_count} run${experiment.run_count === 1 ? "" : "s"} recorded.`}
      />

      <Panel className="space-y-4">
        <SectionTitle title="Metadata" description="Backend-owned experiment identity and declared metrics." />
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-3">
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Tracked metrics</p>
            <div className="flex flex-wrap gap-2">
              {experiment.logged_data_template.map((metric: string) => (
                <span key={metric} className="rounded-full border border-border bg-paper px-3 py-1 font-mono text-xs">
                  {metric}
                </span>
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Labels</p>
            <LabelChips labels={experiment.labels} />
          </div>
        </div>
      </Panel>

      <Panel className="space-y-5">
        <SectionTitle title="Runs" description="Experiment observability lives at the run level. Open a run to inspect its saved Grafana plots." />
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_170px_175px]">
          <SearchInput placeholder="Search runs by number, status, dataset" value={search} onChange={(value) => { setSearch(value); setOffset(0); }} />
          <SelectInput
            onValueChange={(value) => { setSortBy(value); setOffset(0); }}
            options={[
              { value: "run_number", label: "Run number" },
              { value: "created_at", label: "Created" },
              { value: "status", label: "Status" },
            ]}
            value={sortBy}
          />
          <SelectInput
            onValueChange={(value) => { setSortDir(value as "asc" | "desc"); setOffset(0); }}
            options={[
              { value: "desc", label: "Descending" },
              { value: "asc", label: "Ascending" },
            ]}
            value={sortDir}
          />
        </div>
        {runs.items.length === 0 ? (
          <EmptyState title="No runs yet" description="Start a run through the SDK and it will appear here with status and latest metrics." />
        ) : (
          <div className="space-y-4">
            <PaginationControls total={runs.total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
            <div className="space-y-3">
            {runs.items.map((run: (typeof runs.items)[number]) => {
              const latestMetrics = Object.entries(run.latest_metrics) as Array<[string, number]>;
              const visibleMetrics = latestMetrics.slice(0, MAX_VISIBLE_RUN_METRICS);
              const hiddenMetrics = latestMetrics.slice(MAX_VISIBLE_RUN_METRICS);

              return (
                <div key={run.run_number} className="rounded-[24px] border border-border bg-paper/70 p-5 transition hover:border-accent/40">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-3">
                          <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Run {run.run_number}</p>
                          <StatusBadge status={run.status} />
                        </div>
                        <p className="text-sm text-stone-600">
                          Started {formatDateTime(run.created_at)} {run.ended_at ? `• Ended ${formatDateTime(run.ended_at)}` : ""}
                        </p>
                      </div>
                      <LabelChips labels={run.labels} />
                    </div>

                    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] xl:min-w-[460px]">
                      <div className="space-y-2 text-sm text-stone-700">
                        <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Latest metrics</p>
                        {latestMetrics.length === 0 ? (
                          <p className="text-sm text-stone-500">No logged values yet</p>
                        ) : (
                          <div className="space-y-2">
                            <div className="space-y-1">
                              {visibleMetrics.map(([metric, value]) => (
                                <div key={metric} className="flex items-center justify-between gap-4">
                                  <span>{metric}</span>
                                  <span className="font-mono">{formatNumber(value)}</span>
                                </div>
                              ))}
                            </div>
                            {hiddenMetrics.length > 0 ? (
                              <div className="group relative inline-flex">
                                <button
                                  className="inline-flex items-center rounded-full border border-border bg-white/80 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.14em] text-stone-500 transition hover:border-accent/35 hover:text-ink focus:border-accent/35 focus:text-ink focus:outline-none"
                                  type="button"
                                >
                                  +{hiddenMetrics.length} more
                                </button>
                                <div className="pointer-events-none absolute right-0 top-full z-20 mt-2 hidden w-[320px] rounded-[20px] border border-border bg-mist/95 p-4 shadow-card backdrop-blur group-hover:block group-focus-within:block">
                                  <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-stone-500">All metrics</p>
                                  <div className="mt-3 space-y-1.5">
                                    {latestMetrics.map(([metric, value]) => (
                                      <div key={metric} className="flex items-center justify-between gap-4 text-sm text-stone-700">
                                        <span className="min-w-0 truncate">{metric}</span>
                                        <span className="shrink-0 whitespace-nowrap text-right font-mono">{formatNumber(value)}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2 md:justify-end">
                        <Link
                          className="inline-flex items-center justify-center rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-stone-800"
                          to={`/experiments/${slug}/runs/${run.run_number}`}
                        >
                          Open run
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
            </div>
            <PaginationControls total={runs.total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
          </div>
        )}
      </Panel>
    </div>
  );
}
