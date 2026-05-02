import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LabelChips, LoadingCard, PageHeader, PaginationControls, SearchInput, SelectInput, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";

const PAGE_SIZE = 12;

export function ExperimentsPage() {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);
  const experimentsQuery = useQuery({
    queryKey: ["experiments", { search, sortBy, sortDir, offset }],
    queryFn: () => api.listExperimentsPage({ search, sort_by: sortBy, sort_dir: sortDir, limit: PAGE_SIZE, offset }),
  });

  if (experimentsQuery.isLoading) {
    return <LoadingCard label="Loading experiments" />;
  }

  if (experimentsQuery.isError) {
    return <ErrorState description="The experiment list could not be loaded." />;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Experiment Tracking"
        title="Experiments"
        description="Search across experiment groups, inspect their declared metrics, and jump straight into runs and plots."
        action={
          <div className="grid w-full gap-3 md:max-w-2xl md:grid-cols-[minmax(0,1fr)_170px_175px]">
            <SearchInput placeholder="Search by name, slug, or metric" value={search} onChange={(value) => { setSearch(value); setOffset(0); }} />
            <SelectInput
              onValueChange={(value) => { setSortBy(value); setOffset(0); }}
              options={[
                { value: "created_at", label: "Newest" },
                { value: "name", label: "Name" },
                { value: "run_count", label: "Runs" },
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
        }
      />

      {experimentsQuery.data?.items.length === 0 ? (
        <EmptyState title="No experiments found" description="The current filter returned nothing. Clear the search or create activity through the SDK." />
      ) : (
        <div className="space-y-4">
          <PaginationControls total={experimentsQuery.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
          <div className="grid gap-4">
          {experimentsQuery.data?.items.map((experiment) => (
            <Link key={experiment.slug} className="block rounded-[28px] border border-border bg-mist/80 p-6 shadow-card transition hover:border-accent/40" to={`/experiments/${experiment.slug}`}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-4">
                  <div className="space-y-2">
                    <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{experiment.slug}</p>
                    <h2 className="text-2xl font-semibold tracking-[-0.04em]">{experiment.name}</h2>
                    <p className="text-sm text-stone-600">
                      Created {formatDateTime(experiment.created_at)}.
                    </p>
                  </div>
                  <LabelChips labels={experiment.labels} />
                </div>

                <div className="grid gap-3 text-sm text-stone-700 md:grid-cols-3 md:items-start md:text-center">
                  <div className="min-w-[92px]">
                    <p className="font-mono text-xs uppercase tracking-[0.2em] text-stone-500">Runs</p>
                    <p className="mt-1 text-lg font-semibold">{experiment.run_count}</p>
                  </div>
                  <div className="min-w-[92px]">
                    <p className="font-mono text-xs uppercase tracking-[0.2em] text-stone-500">Metrics</p>
                    <p className="mt-1 text-lg font-semibold">{experiment.logged_data_template.length}</p>
                  </div>
                  <div className="min-w-[140px]">
                    <p className="font-mono text-xs uppercase tracking-[0.2em] text-stone-500">Latest</p>
                    <div className="mt-1 flex min-h-9 items-center justify-center">
                      {experiment.latest_run ? <StatusBadge status={experiment.latest_run.status} /> : <p className="text-sm">No runs yet</p>}
                    </div>
                  </div>
                </div>
              </div>
            </Link>
          ))}
          </div>
          <PaginationControls total={experimentsQuery.data?.total ?? 0} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
        </div>
      )}
    </div>
  );
}
