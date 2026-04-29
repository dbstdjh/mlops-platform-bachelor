import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { ErrorState, LabelChips, LoadingCard, PageHeader, Panel, PrimaryButton, SectionTitle, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/date";

export function DatasetDetailPage() {
  const { slug = "", version = "1" } = useParams();
  const versionNumber = Number(version);
  const [downloadState, setDownloadState] = useState<"idle" | "loading" | "error">("idle");

  const datasetQuery = useQuery({
    queryKey: ["dataset", slug, versionNumber],
    queryFn: () => api.getDataset(slug, versionNumber),
  });

  async function handleDownload() {
    setDownloadState("loading");
    try {
      const response = await api.getDatasetDownload(slug, versionNumber);
      window.open(response.download_url, "_blank", "noopener,noreferrer");
      setDownloadState("idle");
    } catch {
      setDownloadState("error");
    }
  }

  if (datasetQuery.isLoading) {
    return <LoadingCard label="Loading dataset version" />;
  }

  if (datasetQuery.isError) {
    const error = datasetQuery.error;
    return (
      <ErrorState
        description={
          error instanceof ApiError ? error.detail : "The requested dataset version could not be loaded."
        }
      />
    );
  }

  const dataset = datasetQuery.data;
  if (!dataset) {
    return null;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Dataset Version"
        title={`${dataset.name} · v${dataset.version}`}
        description={`Slug ${dataset.slug}. Review this version's metadata and download it when you need it.`}
        action={
          <PrimaryButton disabled={downloadState === "loading"} onClick={handleDownload} type="button">
            {downloadState === "loading" ? "Preparing download..." : "Download dataset"}
          </PrimaryButton>
        }
      />

      <Panel className="space-y-5">
        <SectionTitle title="Version metadata" description="Read-only registry details returned by the existing API." />
        <div className="grid gap-4 md:grid-cols-2">
          <Meta label="Status"><StatusBadge status={dataset.status} /></Meta>
          <Meta label="File type">{dataset.file_type ?? "Unknown"}</Meta>
          <Meta label="Created at">{formatDateTime(dataset.created_at)}</Meta>
          <Meta label="Public identity">{dataset.slug} / {dataset.version}</Meta>
        </div>
        <div className="space-y-3">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Labels</p>
          <LabelChips labels={dataset.labels} />
        </div>
        {downloadState === "error" ? (
          <p className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
            This dataset could not be downloaded right now.
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
