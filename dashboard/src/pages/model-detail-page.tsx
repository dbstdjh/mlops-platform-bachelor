import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ErrorState, LabelChips, LoadingCard, PageHeader, Panel, PrimaryButton, SectionTitle, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";

export function ModelDetailPage() {
  const { slug = "", version = "" } = useParams();
  const [downloadState, setDownloadState] = useState<"idle" | "loading" | "error">("idle");

  const modelQuery = useQuery({
    queryKey: ["model", slug, version],
    queryFn: () => api.getModel(slug, version),
  });

  async function handleDownload() {
    setDownloadState("loading");
    try {
      const response = await api.getModelDownload(slug, version);
      window.open(response.download_url, "_blank", "noopener,noreferrer");
      setDownloadState("idle");
    } catch {
      setDownloadState("error");
    }
  }

  if (modelQuery.isLoading) {
    return <LoadingCard label="Loading model version" />;
  }

  if (modelQuery.isError) {
    return <ErrorState description="The requested model version could not be loaded." />;
  }

  const model = modelQuery.data;
  if (!model) {
    return null;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Model Version"
        title={`${model.name} · ${model.version}`}
        description={`Repository ${model.repository_slug}. Review this version's metadata, linked run, and download it when needed.`}
        action={
          <PrimaryButton disabled={downloadState === "loading"} onClick={handleDownload} type="button">
            {downloadState === "loading" ? "Preparing download..." : "Download model artifact"}
          </PrimaryButton>
        }
      />

      <Panel className="space-y-5">
        <SectionTitle title="Version metadata" description="Registry details and linked experiment reference." />
        <div className="grid gap-4 md:grid-cols-2">
          <Meta label="Status"><StatusBadge status={model.status} /></Meta>
          <Meta label="Created at">{formatDateTime(model.created_at)}</Meta>
          <Meta label="Repository">{model.repository_slug}</Meta>
          <Meta label="Deleted">{model.is_deleted ? "Yes" : "No"}</Meta>
        </div>

        <div className="space-y-3">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Labels</p>
          <LabelChips labels={model.labels} />
        </div>

        <div className="space-y-3">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Run linkage</p>
          {model.run ? (
            <Link
              className="inline-flex rounded-2xl border border-border bg-paper px-4 py-3 text-sm font-semibold hover:border-accent hover:text-accent"
              to={`/experiments/${model.run.experiment_slug}/runs/${model.run.run_number}`}
            >
              View run {model.run.run_number} in {model.run.experiment_slug}
            </Link>
          ) : (
            <p className="text-sm text-stone-500">No run reference linked to this model version.</p>
          )}
        </div>

        {downloadState === "error" ? (
          <p className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
            This model artifact could not be downloaded right now.
          </p>
        ) : null}
      </Panel>
    </div>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-paper/75 p-4">
      <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{label}</p>
      <div className="mt-2 text-sm text-stone-700">{children}</div>
    </div>
  );
}
