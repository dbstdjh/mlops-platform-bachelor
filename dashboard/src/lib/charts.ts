import type { ExperimentMetricPlot, PlotPoint, RunMetricPlot } from "@/types/api";

export interface MultiSeriesChartPoint {
  step: number;
  [seriesKey: string]: number;
}

export function buildRunMetricChartData(plot: RunMetricPlot): PlotPoint[] {
  return [...plot.points].sort((left, right) => left.step - right.step);
}

export function buildExperimentMetricChartData(plot: ExperimentMetricPlot): MultiSeriesChartPoint[] {
  const rows = new Map<number, MultiSeriesChartPoint>();

  for (const series of plot.series) {
    const key = `run_${series.run.run_number}`;
    for (const point of series.points) {
      const current = rows.get(point.step) ?? { step: point.step };
      current[key] = point.val;
      rows.set(point.step, current);
    }
  }

  return Array.from(rows.values()).sort((left, right) => left.step - right.step);
}
