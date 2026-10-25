import { formatCell } from "@/lib/format";
import type { Result } from "@/lib/types";

const CLASS_STYLE: Record<string, string> = {
  confidential: "border-amber-400 text-amber-700 dark:text-amber-300",
  public: "border-emerald-400 text-emerald-700 dark:text-emerald-300",
};

export function ResultTable({ result }: { result: Result }) {
  return (
    <section className="card overflow-hidden p-0">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <p className="label">Result</p>
        <p className="text-xs text-muted">
          {result.row_count} row{result.row_count === 1 ? "" : "s"}
          {result.truncated && " (truncated by the row limit)"}
        </p>
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b border-border text-left">
              {result.columns.map((column) => (
                <th key={column.name} className="px-5 py-2 align-bottom font-medium">
                  <div>{column.name}</div>
                  {column.classification && (
                    <span
                      className={`badge mt-1 ${CLASS_STYLE[column.classification] ?? ""}`}
                      title={column.sources.join(", ") || "computed"}
                    >
                      {column.classification}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, r) => (
              <tr key={r} className="border-b border-border/60 last:border-0">
                {row.map((cell, c) => (
                  <td
                    key={c}
                    className="px-5 py-1.5 tabular-nums"
                    title={cell === null ? "null" : String(cell)}
                  >
                    {formatCell(cell, result.columns[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
