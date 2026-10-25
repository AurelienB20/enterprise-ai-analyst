"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { chartData, chooseChart } from "@/lib/chart";
import { formatCell } from "@/lib/format";
import type { Result } from "@/lib/types";

const COLORS = ["#4f46e5", "#0891b2", "#d97706"];

const compact = (value: number) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);

export function ResultChart({ result }: { result: Result }) {
  const spec = chooseChart(result);
  if (spec.kind === "table") return null;

  if (spec.kind === "kpi") {
    const column = result.columns[spec.column];
    return (
      <section className="card">
        <p className="label">{spec.label}</p>
        <p className="mt-2 text-4xl font-semibold tracking-tight">
          {formatCell(result.rows[0][spec.column], column)}
        </p>
      </section>
    );
  }

  const labelIndex = spec.kind === "line" ? spec.x : spec.category;
  const data = chartData(result, labelIndex, spec.series).map((point) => ({
    ...point,
    label: formatCell(point.label, result.columns[labelIndex]),
  }));
  const names = spec.series.map((index) => result.columns[index].name);

  return (
    <section className="card">
      <p className="label mb-4">
        {names.join(", ")} by {result.columns[labelIndex].name}
        <span className="ml-2 normal-case font-normal">(drawn from the rows below)</span>
      </p>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {spec.kind === "line" ? (
            <LineChart data={data} margin={{ left: 8, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={compact} tick={{ fontSize: 12 }} width={60} />
              <Tooltip />
              {names.map((name, i) => (
                <Line key={name} dataKey={name} stroke={COLORS[i]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          ) : (
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis type="number" tickFormatter={compact} tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="label" width={170} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey={names[0]} fill={COLORS[0]} radius={[0, 4, 4, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}
