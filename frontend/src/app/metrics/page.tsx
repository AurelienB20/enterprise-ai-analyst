import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { getJson } from "@/lib/backend";
import { formatCost, formatDuration } from "@/lib/format";

export const metadata: Metadata = { title: "Metrics · Enterprise AI Analyst" };

interface Stats {
  days: number;
  analyses: number;
  answered: number;
  declined: number;
  rejected: number;
  failed: number;
  sql_proposals: number;
  sql_rejected_by_validator: number;
  sql_timeouts: number;
  permission_violations: number;
  llm_errors: number;
  explanations_verified: number;
  explanations_withheld: number;
  questions_with_personal_data_masked: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="card">
      <p className="label">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

const pct = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)} %` : "—");

export default async function MetricsPage() {
  await connection(); // read at request time, never at build time
  const stats = await getJson<Stats>("/analyses/stats?days=7");

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-6">
      <header className="mb-8">
        <Link href="/" className="text-sm text-muted hover:text-accent">
          ← Back to the analyst
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Service metrics</h1>
        <p className="mt-2 text-muted">
          Last 7 days, from the audit trail. Aggregates only: no question and no result value
          is shown here.
        </p>
      </header>
      {stats === null ? (
        <p className="card text-sm">The metrics are not available right now.</p>
      ) : (
        <div className="space-y-8">
          <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Tile label="Analyses" value={String(stats.analyses)} />
            <Tile label="Answered" value={pct(stats.answered, stats.analyses)} note={`${stats.answered}`} />
            <Tile label="Declined" value={String(stats.declined)} note="personal data, not allowed, not in data" />
            <Tile label="Failed" value={String(stats.failed + stats.rejected)} note={`${stats.llm_errors} provider errors`} />
          </section>
          <section>
            <h2 className="label mb-3">Security and privacy</h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Tile
                label="SQL rejected by the validator"
                value={String(stats.sql_rejected_by_validator)}
                note={`of ${stats.sql_proposals} proposals`}
              />
              <Tile label="Query timeouts" value={String(stats.sql_timeouts)} />
              <Tile label="Permission violations" value={String(stats.permission_violations)} note="should stay 0" />
              <Tile
                label="Questions with personal data masked"
                value={String(stats.questions_with_personal_data_masked)}
              />
            </div>
          </section>
          <section>
            <h2 className="label mb-3">Quality, speed, cost</h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Tile
                label="Explanations verified"
                value={pct(stats.explanations_verified, stats.explanations_verified + stats.explanations_withheld)}
                note={`${stats.explanations_withheld} withheld`}
              />
              <Tile
                label="Latency p50 / p95"
                value={stats.latency_p50_ms === null ? "—" : formatDuration(stats.latency_p50_ms)}
                note={stats.latency_p95_ms === null ? undefined : `p95 ${formatDuration(stats.latency_p95_ms)}`}
              />
              <Tile
                label="Tokens"
                value={`${Math.round((stats.input_tokens + stats.output_tokens) / 1000)}k`}
                note={`${Math.round(stats.output_tokens / 1000)}k out`}
              />
              <Tile
                label="LLM cost"
                value={formatCost(Number(stats.cost_usd))}
                note={stats.analyses ? `${formatCost(Number(stats.cost_usd) / stats.analyses)} per analysis` : undefined}
              />
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
