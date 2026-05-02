import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LabelChips, LoadingCard, PageHeader, PaginationControls, SearchInput, SelectInput, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";

const PAGE_SIZE = 12;

export function RepositoriesPage() {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);
  const repositoriesQuery = useQuery({
    queryKey: ["repositories", { search, sortBy, sortDir, offset }],
    queryFn: () => api.listRepositoriesPage({ search, sort_by: sortBy, sort_dir: sortDir, limit: PAGE_SIZE, offset }),
  });

  if (repositoriesQuery.isLoading) {
    return <LoadingCard label="Loading repositories" />;
  }

  if (repositoriesQuery.isError) {
    return <ErrorState description="Model repositories could not be loaded." />;
  }

  if (!repositoriesQuery.data) {
    return null;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Model Registry"
        title="Repositories"
        description="Each repository is an immutable public slug that will collect model versions linked to runs."
        action={
          <div className="grid w-full gap-3 md:max-w-2xl md:grid-cols-[minmax(0,1fr)_170px_175px]">
            <SearchInput placeholder="Search by name or slug" value={search} onChange={(value) => { setSearch(value); setOffset(0); }} />
            <SelectInput
              onValueChange={(value) => { setSortBy(value); setOffset(0); }}
              options={[
                { value: "created_at", label: "Newest" },
                { value: "name", label: "Name" },
                { value: "slug", label: "Slug" },
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

      {repositoriesQuery.data.items.length === 0 ? (
        <EmptyState title="No repositories yet" description="Create one through the API or SDK-backed workflow and it will appear here." />
      ) : (
        <div className="space-y-4">
          <PaginationControls total={repositoriesQuery.data.total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
          <div className="grid gap-4">
          {repositoriesQuery.data.items.map((repository: (typeof repositoriesQuery.data.items)[number]) => (
            <Link
              key={repository.slug}
              className="block rounded-[28px] border border-border bg-mist/80 p-6 shadow-card transition hover:border-accent/40"
              to={`/repositories/${repository.slug}`}
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-3">
                  <div>
                    <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{repository.slug}</p>
                    <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">{repository.name}</h2>
                    <p className="mt-1 text-sm text-stone-600">Created {formatDateTime(repository.created_at)}</p>
                  </div>
                  <LabelChips labels={repository.labels} />
                </div>
                <StatusBadge status={repository.is_deleted ? "DELETED" : "ACTIVE"} />
              </div>
            </Link>
          ))}
          </div>
          <PaginationControls total={repositoriesQuery.data.total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
        </div>
      )}
    </div>
  );
}
