// Display of result cells. The exact value is kept for the table's title attribute; the
// display only adds grouping and a sensible number of decimals.

import type { Cell, Column } from "./types";
import { isNumericColumn, toNumber } from "./chart";

const RATIO_NAME = /(rate|ratio|share|growth|pct|percent|taux|part|croissance|variation_pct)/i;

export function formatCell(cell: Cell, column: Column, locale = "fr-FR"): string {
  if (cell === null) return "—";
  if (typeof cell === "boolean") return cell ? "✓" : "✗";
  if (isNumericColumn(column)) {
    const value = toNumber(cell);
    if (value === null) return String(cell);
    if (RATIO_NAME.test(column.name) && Math.abs(value) <= 1.5) {
      return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(value);
    }
    const decimals = Number.isInteger(value) ? 0 : 2;
    return new Intl.NumberFormat(locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value);
  }
  if (column.type.startsWith("timestamp") && typeof cell === "string") {
    return cell.endsWith("T00:00:00") ? cell.slice(0, 10) : cell.replace("T", " ");
  }
  return String(cell);
}

export function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function formatCost(usd: number): string {
  return `$${usd.toFixed(4)}`;
}
