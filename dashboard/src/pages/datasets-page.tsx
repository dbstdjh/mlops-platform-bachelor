import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LabelChips, LoadingCard, PageHeader, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { groupDatasets } from "@/lib/datasets";

export function DatasetsPage() {
  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: async () => groupDatasets(await api.listDatasets()),
  });

  if (datasetsQuery.isLoading) {
    return <LoadingCard label="Loading datasets" />;
  }

  if (datasetsQuery.isError) {
    return <ErrorState description="Dataset versions could not be loaded." />;
  }

  if (!datasetsQuery.data) {
    return null;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Feature Registry"
        title="Datasets"
        description="Logical dataset groups are assembled on the client from version rows returned by the control plane."
      />

      {datasetsQuery.data.length === 0 ? (
        <EmptyState title="No datasets yet" description="Uploads initiated through the SDK will appear here once recorded by the control plane." />
      ) : (
        <div className="grid gap-4">
          {datasetsQuery.data.map((group: (typeof datasetsQuery.data)[number]) => (
            <div key={group.slug} className="rounded-[28px] border border-border bg-mist/80 p-6 shadow-card">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-3">
                  <div>
                    <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{group.slug}</p>
                    <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">{group.name}</h2>
                    <p className="mt-1 text-sm text-stone-600">
                      Latest version v{group.latest.version} • Created {formatDateTime(group.latest.created_at)}
                    </p>
                  </div>
                  <LabelChips labels={group.latest.labels} />
                </div>

                <div className="flex items-center gap-3">
                  <StatusBadge status={group.latest.status} />
                  <Link
                    className="rounded-full border border-border bg-paper px-4 py-3 text-sm font-semibold hover:border-accent hover:text-accent"
                    to={`/datasets/${group.slug}/versions/${group.latest.version}`}
                  >
                    View latest
                  </Link>
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {group.versions.map((version) => (
                  <Link
                    key={`${version.slug}-${version.version}`}
                    className="rounded-2xl border border-border bg-paper/70 px-4 py-4 transition hover:border-accent/40"
                    to={`/datasets/${version.slug}/versions/${version.version}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold">Version {version.version}</p>
                      <StatusBadge status={version.status} />
                    </div>
                    <p className="mt-2 text-sm text-stone-600">{version.file_type ?? "unknown"} • {formatDateTime(version.created_at)}</p>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
