// Which visualisation fits a result, decided by code from the columns' types: the
// model never chooses, and never supplies the data of a chart. Every point drawn is a
// cell of the result the SQL returned.

import type { Cell, Column, Result } from "./types";

export type ChartSpec =
  | { kind: "kpi"; label: string; value: number; column: number }
  | { kind: "line"; x: number; series: number[] }
  | { kind: "bar"; category: number; series: number[] }
  | { kind: "table" };

const NUMERIC = new Set(["numeric", "int2", "int4", "int8", "float4", "float8"]);
const TEMPORAL = new Set(["date", "timestamp", "timestamptz"]);
const MAX_BARS = 25;
const MAX_SERIES = 3;

export function isNumericColumn(column: Column): boolean {
  return NUMERIC.has(column.type);
}

export function toNumber(cell: Cell): number | null {
  if (typeof cell === "number") return cell;
  if (typeof cell === "string" && cell.trim() !== "" && !Number.isNaN(Number(cell))) {
    return Number(cell);
  }
  return null;
}

// Identifiers are numbers that should not be drawn (customer_id, order_id...).
function isIdentifier(column: Column): boolean {
  return /(^id$|_id$)/.test(column.name);
}

function isMonotonic(values: (number | null)[]): boolean {
  if (values.some((v) => v === null) || new Set(values).size < 2) return false;
  const numbers = values as number[];
  const pairs = numbers.slice(1).map((value, i) => value - numbers[i]);
  return pairs.every((d) => d >= 0) || pairs.every((d) => d <= 0);
}

export function chooseChart(result: Result): ChartSpec {
  const { columns, rows } = result;
  if (rows.length === 0) return { kind: "table" };
  const numeric = columns
    .map((column, index) => ({ column, index }))
    .filter(({ column }) => isNumericColumn(column) && !isIdentifier(column))
    .map(({ index }) => index);

  if (rows.length === 1 && columns.length === 1 && numeric.length === 1) {
    const value = toNumber(rows[0][0]);
    if (value !== null) return { kind: "kpi", label: columns[0].name, value, column: 0 };
  }
  if (numeric.length === 0) return { kind: "table" };
  const series = numeric.slice(0, MAX_SERIES);

  const temporal = columns.findIndex((column) => TEMPORAL.has(column.type));
  if (temporal >= 0 && rows.length >= 2) return { kind: "line", x: temporal, series };

  const category = columns.findIndex(
    (column, index) => !numeric.includes(index) && (column.type === "text" || column.type === "bpchar"),
  );
  if (category >= 0 && rows.length >= 2 && rows.length <= MAX_BARS) {
    // A ranking is drawn on the measure it is ranked by: the column whose values are in
    // order down the rows (the ORDER BY of the query), else the first numeric column.
    const ranked = numeric.find((index) => isMonotonic(rows.map((row) => toNumber(row[index]))));
    return { kind: "bar", category, series: [ranked ?? numeric[0]] };
  }
  return { kind: "table" };
}

/** Rows for Recharts: the label and the numbers of the chosen columns, as numbers. */
export function chartData(
  result: Result,
  label: number,
  series: number[],
): Array<Record<string, string | number | null>> {
  return result.rows.map((row) => {
    const point: Record<string, string | number | null> = { label: String(row[label] ?? "") };
    for (const index of series) point[result.columns[index].name] = toNumber(row[index]);
    return point;
  });
}
