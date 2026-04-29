import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { buildExperimentMetricChartData, buildRunMetricChartData } from "@/lib/charts";
import { formatNumber } from "@/lib/utils";
import type { ExperimentMetricPlot, RunMetricPlot } from "@/types/api";

const palette = ["#c7683f", "#50624d", "#8f5b42", "#7b756c", "#9a7c53"];

export function ExperimentMetricChart({ plot }: { plot: ExperimentMetricPlot }) {
  const data = buildExperimentMetricChartData(plot);

  if (data.length === 0) {
    return <p className="text-sm text-stone-500">No plot points have been logged for this metric yet.</p>;
  }

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid stroke="#d4c8bb" strokeDasharray="4 4" />
          <XAxis dataKey="step" stroke="#6d645a" tickLine={false} axisLine={false} />
          <YAxis stroke="#6d645a" tickLine={false} axisLine={false} tickFormatter={formatNumber} />
          <Tooltip />
          <Legend />
          {plot.series.map((series, index) => (
            <Line
              key={series.run.run_number}
              type="monotone"
              dataKey={`run_${series.run.run_number}`}
              stroke={palette[index % palette.length]}
              strokeWidth={2.5}
              dot={false}
              name={`Run ${series.run.run_number}`}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RunMetricChart({ plot }: { plot: RunMetricPlot }) {
  const data = buildRunMetricChartData(plot);

  if (data.length === 0) {
    return <p className="text-sm text-stone-500">No points have been logged for this metric yet.</p>;
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid stroke="#d4c8bb" strokeDasharray="4 4" />
          <XAxis dataKey="step" stroke="#6d645a" tickLine={false} axisLine={false} />
          <YAxis stroke="#6d645a" tickLine={false} axisLine={false} tickFormatter={formatNumber} />
          <Tooltip />
          <Line type="monotone" dataKey="val" stroke="#c7683f" strokeWidth={2.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
