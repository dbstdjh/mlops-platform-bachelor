import { buildExperimentMetricChartData, buildRunMetricChartData } from "@/lib/charts";

describe("chart helpers", () => {
  it("sorts single-run plots by step", () => {
    const data = buildRunMetricChartData({
      metric_name: "loss",
      points: [
        { step: 3, val: 0.3, timestamp: "2026-04-01T10:00:00Z" },
        { step: 1, val: 0.9, timestamp: "2026-04-01T09:00:00Z" },
      ],
    });

    expect(data.map((item) => item.step)).toEqual([1, 3]);
  });

  it("merges experiment series by step", () => {
    const data = buildExperimentMetricChartData({
      metric_name: "loss",
      series: [
        {
          run: { experiment_slug: "iris", run_number: 1 },
          points: [{ step: 1, val: 0.9, timestamp: "2026-04-01T09:00:00Z" }],
        },
        {
          run: { experiment_slug: "iris", run_number: 2 },
          points: [{ step: 1, val: 0.8, timestamp: "2026-04-01T09:00:00Z" }],
        },
      ],
    });

    expect(data).toEqual([{ step: 1, run_1: 0.9, run_2: 0.8 }]);
  });
});
