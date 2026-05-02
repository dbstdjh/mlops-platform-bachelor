import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Panel, EmptyState, ErrorState, LoadingCard, PageHeader, SectionTitle, StatCard, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, formatRelativeTime } from "@/lib/date";
import { groupDatasets } from "@/lib/datasets";
import { formatCount } from "@/lib/utils";

export function OverviewPage() {
  const overviewQuery = useQuery({
    queryKey: ["overview"],
    queryFn: async () => {
      const [user, summary, recent] = await Promise.all([
        api.getMe(),
        api.getOverviewSummary(),
        api.getOverviewRecent(),
      ]);

      return {
        user,
        summary,
        experiments: recent.experiments,
        datasetGroups: groupDatasets(recent.datasets),
        repositories: recent.repositories,
        deployments: recent.deployments,
      };
    },
  });

  if (overviewQuery.isLoading) {
    return (
      <div className="space-y-6">
        <LoadingCard label="Loading overview" />
        <LoadingCard label="Collecting recent activity" />
      </div>
    );
  }

  if (overviewQuery.isError) {
    return <ErrorState description="The dashboard could not load overview data from the control plane." />;
  }

  if (!overviewQuery.data) {
    return null;
  }

  const { user, summary, experiments, datasetGroups, repositories, deployments } = overviewQuery.data;
  const recentExperiments = experiments.slice(0, 3);
  const recentDatasets = datasetGroups.slice(0, 3);
  const recentRepositories = repositories.slice(0, 3);
  const recentDeployments = deployments.slice(0, 3);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Overview"
        title="A clean snapshot of the platform"
        description={`Signed in as ${user.email}. This front page stays intentionally light and read-oriented so you can see experiments, data assets, and registry activity at a glance.`}
      />

      <div className="grid gap-4 xl:grid-cols-4">
        <StatCard label="Experiments" value={formatCount(summary.experiment_count)} detail="Defined training groups currently visible to your account." />
        <StatCard label="Datasets" value={formatCount(summary.dataset_count)} detail="Dataset version records stored in the feature registry." />
        <StatCard label="Repositories" value={formatCount(summary.repository_count)} detail="Model repositories that hold versioned artifacts." />
        <StatCard label="Deployments" value={formatCount(summary.deployment_count)} detail="Serving endpoints tracked by the control plane." />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Panel className="space-y-5">
          <SectionTitle
            title="Recent experiments"
            description="Latest activity and terminal state from the experiment tracker."
            linkLabel="See all experiments"
            linkTo="/experiments"
          />
          {recentExperiments.length === 0 ? (
            <EmptyState
              title="No experiments yet"
              description="Once the SDK starts runs through the control plane, your experiments will appear here."
            />
          ) : (
            <div className="space-y-3">
              {recentExperiments.map((experiment: (typeof recentExperiments)[number]) => (
                <Link
                  key={experiment.slug}
                  className="block rounded-[24px] border border-border bg-paper/80 p-5 transition hover:border-accent/40"
                  to={`/experiments/${experiment.slug}`}
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="space-y-2">
                      <p className="font-mono text-xs uppercase tracking-[0.22em] text-stone-500">{experiment.slug}</p>
                      <h3 className="text-xl font-semibold tracking-[-0.03em]">{experiment.name}</h3>
                      <p className="text-sm text-stone-600">
                        {experiment.run_count} run{experiment.run_count === 1 ? "" : "s"} tracked. Created{" "}
                        {formatRelativeTime(experiment.created_at)}.
                      </p>
                    </div>
                    {experiment.latest_run ? <StatusBadge status={experiment.latest_run.status} /> : null}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Panel>

        <Panel className="space-y-5">
          <SectionTitle title="Recent assets" description="The newest dataset and repository records." />
          <div className="space-y-4">
            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Datasets</p>
              {recentDatasets.length === 0 ? (
                <p className="text-sm text-stone-500">No datasets uploaded yet.</p>
              ) : (
                recentDatasets.map((dataset: (typeof recentDatasets)[number]) => (
                  <Link
                    key={dataset.slug}
                    className="flex items-center justify-between rounded-2xl border border-border bg-paper/70 px-4 py-3"
                    to={`/datasets/${dataset.slug}/versions/${dataset.latest.version}`}
                  >
                    <div>
                      <p className="font-semibold">{dataset.name}</p>
                      <p className="text-xs text-stone-500">Latest version: v{dataset.latest.version}</p>
                    </div>
                    <StatusBadge status={dataset.latest.status} />
                  </Link>
                ))
              )}
            </div>

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Repositories</p>
              {recentRepositories.length === 0 ? (
                <p className="text-sm text-stone-500">No repositories created yet.</p>
              ) : (
                recentRepositories.map((repository: (typeof recentRepositories)[number]) => (
                  <Link
                    key={repository.slug}
                    className="flex items-center justify-between rounded-2xl border border-border bg-paper/70 px-4 py-3"
                    to={`/repositories/${repository.slug}`}
                  >
                    <div>
                      <p className="font-semibold">{repository.name}</p>
                      <p className="text-xs text-stone-500">Created {formatDateTime(repository.created_at)}</p>
                    </div>
                    <span className="font-mono text-xs uppercase tracking-[0.2em] text-stone-500">{repository.slug}</span>
                  </Link>
                ))
              )}
            </div>

            <div className="space-y-3">
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Deployments</p>
              {recentDeployments.length === 0 ? (
                <p className="text-sm text-stone-500">No deployments created yet.</p>
              ) : (
                recentDeployments.map((deployment: (typeof recentDeployments)[number]) => (
                  <Link
                    key={deployment.slug}
                    className="flex items-center justify-between rounded-2xl border border-border bg-paper/70 px-4 py-3"
                    to={`/deployments/${deployment.slug}`}
                  >
                    <div>
                      <p className="font-semibold">{deployment.name}</p>
                      <p className="text-xs text-stone-500">Created {formatDateTime(deployment.created_at)}</p>
                    </div>
                    <StatusBadge status={deployment.status} />
                  </Link>
                ))
              )}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
