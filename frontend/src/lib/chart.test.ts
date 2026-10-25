import { describe, expect, it } from "vitest";

import { chartData, chooseChart } from "./chart";
import { formatCell } from "./format";
import type { Column, Result } from "./types";

const col = (name: string, type: string): Column => ({
  name,
  type,
  classification: "internal",
  sources: [],
});

function result(columns: Column[], rows: Result["rows"]): Result {
  return { columns, rows, row_count: rows.length, truncated: false };
}

describe("chooseChart", () => {
  it("shows a single number as a KPI", () => {
    expect(chooseChart(result([col("revenue", "numeric")], [["123.45"]]))).toEqual({
      kind: "kpi",
      label: "revenue",
      value: 123.45,
      column: 0,
    });
  });

  it("draws a time series as a line", () => {
    const spec = chooseChart(
      result(
        [col("month", "timestamp"), col("revenue", "numeric")],
        [
          ["2026-04-01T00:00:00", "10"],
          ["2026-05-01T00:00:00", "12"],
        ],
      ),
    );
    expect(spec).toEqual({ kind: "line", x: 0, series: [1] });
  });

  it("draws a ranking as bars, ignoring identifier columns", () => {
    const spec = chooseChart(
      result(
        [col("customer_id", "int4"), col("customer_name", "text"), col("revenue", "numeric")],
        [
          [1, "A", "10"],
          [2, "B", "5"],
        ],
      ),
    );
    expect(spec).toEqual({ kind: "bar", category: 1, series: [2] });
  });

  it("draws a ranking on the measure it is sorted by", () => {
    const spec = chooseChart(
      result(
        [col("category", "text"), col("q2", "numeric"), col("q3", "numeric"), col("change", "numeric")],
        [
          ["Printing", "1956559", "945703", "-1010856"],
          ["IT Hardware", "804927", "672180", "-132747"],
          ["Safety", "564540", "462889", "-101651"],
          ["Cleaning", "584371", "483972", "-100399"],
        ],
      ),
    );
    expect(spec).toEqual({ kind: "bar", category: 0, series: [3] });
  });

  it("falls back to a table when nothing fits", () => {
    expect(chooseChart(result([col("name", "text")], [["A"], ["B"]]))).toEqual({ kind: "table" });
    expect(chooseChart(result([col("revenue", "numeric")], []))).toEqual({ kind: "table" });
    const many = Array.from({ length: 40 }, (_, i) => [`c${i}`, String(i)]);
    expect(chooseChart(result([col("c", "text"), col("v", "numeric")], many)).kind).toBe("table");
  });

  it("uses the result's own values as chart data", () => {
    const data = chartData(
      result([col("region", "text"), col("revenue", "numeric")], [["North", "10.50"]]),
      0,
      [1],
    );
    expect(data).toEqual([{ label: "North", revenue: 10.5 }]);
  });
});

describe("formatCell", () => {
  it("groups amounts, shows ratios as percentages and keeps nulls visible", () => {
    expect(formatCell("1234567.5", col("revenue", "numeric"), "en-US")).toBe("1,234,567.50");
    expect(formatCell("0.4321", col("growth_rate", "numeric"), "en-US")).toBe("43.2%");
    expect(formatCell(42, col("orders", "int8"), "en-US")).toBe("42");
    expect(formatCell(null, col("revenue", "numeric"))).toBe("—");
    expect(formatCell("2026-04-01T00:00:00", col("month", "timestamp"))).toBe("2026-04-01");
  });
});
