import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LabelChips, LoadingCard, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";

export function RepositoriesPage() {
  const repositoriesQuery = useQuery({
    queryKey: ["repositories"],
    queryFn: api.listRepositories,
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
      />

      {repositoriesQuery.data.length === 0 ? (
        <EmptyState title="No repositories yet" description="Create one through the API or SDK-backed workflow and it will appear here." />
      ) : (
        <div className="grid gap-4">
          {repositoriesQuery.data.map((repository: (typeof repositoriesQuery.data)[number]) => (
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
      )}
    </div>
  );
}
