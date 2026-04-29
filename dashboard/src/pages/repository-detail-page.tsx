import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { EmptyState, ErrorState, LabelChips, LoadingCard, PageHeader, Panel, SectionTitle, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";

export function RepositoryDetailPage() {
  const { slug = "" } = useParams();

  const repositoryQuery = useQuery({
    queryKey: ["repository", slug],
    queryFn: async () => {
      const [repository, models] = await Promise.all([api.getRepository(slug), api.listModels(slug)]);
      return { repository, models };
    },
  });

  if (repositoryQuery.isLoading) {
    return <LoadingCard label="Loading repository" />;
  }

  if (repositoryQuery.isError) {
    return <ErrorState description="The repository detail page could not be loaded." />;
  }

  if (!repositoryQuery.data) {
    return null;
  }

  const { repository, models } = repositoryQuery.data;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Repository"
        title={repository.name}
        description={`Slug ${repository.slug}. Created ${formatDateTime(repository.created_at)}.`}
      />

      <Panel className="space-y-4">
        <SectionTitle title="Repository metadata" description="Stable public identity for grouping related model versions." />
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-border bg-paper/75 p-4">
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Status</p>
            <div className="mt-2">
              <StatusBadge status={repository.is_deleted ? "DELETED" : "ACTIVE"} />
            </div>
          </div>
          <div className="rounded-2xl border border-border bg-paper/75 p-4">
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Models tracked</p>
            <p className="mt-2 text-lg font-semibold">{models.length}</p>
          </div>
        </div>
        <div className="space-y-3">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Labels</p>
          <LabelChips labels={repository.labels} />
        </div>
      </Panel>

      <Panel className="space-y-5">
        <SectionTitle title="Model versions" description="Versions are loaded from the existing repository-scoped API." />
        {models.length === 0 ? (
          <EmptyState title="No model versions yet" description="Once versions are created in this repository, they will show up here." />
        ) : (
          <div className="space-y-3">
            {models.map((model: (typeof models)[number]) => (
              <Link
                key={model.version}
                className="block rounded-[24px] border border-border bg-paper/70 p-5 transition hover:border-accent/40"
                to={`/repositories/${slug}/models/${model.version}`}
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Version {model.version}</p>
                    <h3 className="text-xl font-semibold tracking-[-0.03em]">{model.name}</h3>
                    <p className="text-sm text-stone-600">Created {formatDateTime(model.created_at)}</p>
                    {model.run ? (
                      <p className="text-sm text-stone-600">
                        Linked to run {model.run.run_number} in {model.run.experiment_slug}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-col gap-3 lg:ml-auto lg:min-w-[320px] lg:items-end">
                    <StatusBadge status={model.status} />
                    <div className="lg:flex lg:justify-end">
                      <LabelChips labels={model.labels} />
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
