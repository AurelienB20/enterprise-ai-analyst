import { formatCost, formatDuration } from "@/lib/format";
import type { Analysis } from "@/lib/types";

const OUTCOME_STYLE: Record<string, string> = {
  accepted: "border-emerald-400 text-emerald-700 dark:text-emerald-300",
  rejected: "border-red-400 text-red-700 dark:text-red-300",
  failed: "border-amber-400 text-amber-700 dark:text-amber-300",
};

function Sql({ sql }: { sql: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg bg-background p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">
      {sql}
    </pre>
  );
}

/** Everything needed to check an answer: what was assumed, what ran, what it cost. */
export function AnalysisTrace({ analysis }: { analysis: Analysis }) {
  const { timings, usage } = analysis;
  const rewritten =
    analysis.proposed_sql !== null &&
    analysis.executed_sql !== null &&
    analysis.proposed_sql.trim() !== analysis.executed_sql.trim();

  return (
    <details className="card group" open={analysis.status !== "answered"}>
      <summary className="cursor-pointer list-none">
        <span className="label">AI Analysis Trace</span>
        <span className="ml-2 text-xs text-muted group-open:hidden">
          SQL, assumptions, attempts, data sources, cost
        </span>
      </summary>

      <div className="mt-4 space-y-5 text-sm">
        {analysis.explanation && (
          <div>
            <p className="label mb-1">What the query does</p>
            <p>{analysis.explanation}</p>
          </div>
        )}

        {(analysis.assumptions.length > 0 || analysis.ambiguities.length > 0) && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="label mb-1">Assumptions</p>
              <ul className="list-disc space-y-1 pl-5">
                {analysis.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="label mb-1">Other possible readings</p>
              <ul className="list-disc space-y-1 pl-5 text-muted">
                {analysis.ambiguities.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {analysis.executed_sql && (
          <div>
            <p className="label mb-1">
              SQL that ran{" "}
              <span className="normal-case font-normal">
                (as eaa_reader, read-only, on: {analysis.views.join(", ")})
              </span>
            </p>
            <Sql sql={analysis.executed_sql} />
            {rewritten && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-muted">
                  SQL as proposed by the model (the validator regenerated it)
                </summary>
                <div className="mt-2">
                  <Sql sql={analysis.proposed_sql ?? ""} />
                </div>
              </details>
            )}
          </div>
        )}

        {analysis.attempts.length > 0 && (
          <div>
            <p className="label mb-1">Attempts</p>
            <ol className="space-y-3">
              {analysis.attempts.map((attempt, i) => (
                <li key={i} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted">#{i + 1}</span>
                    <span className={`badge ${OUTCOME_STYLE[attempt.outcome]}`}>
                      {attempt.outcome}
                    </span>
                    {attempt.message && <span className="text-xs">{attempt.message}</span>}
                  </div>
                  {attempt.outcome !== "accepted" && <Sql sql={attempt.sql} />}
                </li>
              ))}
            </ol>
          </div>
        )}

        <div>
          <p className="label mb-1">Cost and timing</p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
            <dt className="text-muted">Model</dt>
            <dd className="font-mono text-xs">{analysis.model}</dd>
            <dt className="text-muted">LLM calls</dt>
            <dd>{usage.llm_calls}</dd>
            <dt className="text-muted">SQL writing</dt>
            <dd>{formatDuration(timings.generation_ms)}</dd>
            <dt className="text-muted">Query</dt>
            <dd>{formatDuration(timings.execution_ms)}</dd>
            <dt className="text-muted">Explanation</dt>
            <dd>{formatDuration(timings.explanation_ms)}</dd>
            <dt className="text-muted">Total</dt>
            <dd>{formatDuration(timings.total_ms)}</dd>
            <dt className="text-muted">Tokens</dt>
            <dd>
              {usage.input_tokens + usage.cache_read_tokens} in ({usage.cache_read_tokens} cached),{" "}
              {usage.output_tokens} out
            </dd>
            <dt className="text-muted">Cost</dt>
            <dd>{formatCost(usage.cost_usd)}</dd>
          </dl>
        </div>
        <p className="text-xs text-muted">Analysis {analysis.id}</p>
      </div>
    </details>
  );
}
