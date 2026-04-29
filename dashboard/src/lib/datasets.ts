import type { Dataset } from "@/types/api";

export interface DatasetGroup {
  slug: string;
  name: string;
  versions: Dataset[];
  latest: Dataset;
}

export function groupDatasets(datasets: Dataset[]): DatasetGroup[] {
  const groups = new Map<string, Dataset[]>();

  for (const dataset of datasets) {
    const current = groups.get(dataset.slug) ?? [];
    current.push(dataset);
    groups.set(dataset.slug, current);
  }

  return Array.from(groups.entries())
    .map(([slug, versions]) => {
      const sorted = [...versions].sort((left, right) => right.version - left.version);
      return {
        slug,
        name: sorted[0]?.name ?? slug,
        versions: sorted,
        latest: sorted[0],
      };
    })
    .sort((left, right) => {
      return new Date(right.latest.created_at).getTime() - new Date(left.latest.created_at).getTime();
    });
}
