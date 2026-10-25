"use client";

import type { Analysis } from "@/lib/types";

import { AnalysisTrace } from "./AnalysisTrace";
import { ResultChart } from "./ResultChart";
import { ResultTable } from "./ResultTable";

const STATUS_TEXT: Record<Analysis["status"], string> = {
  answered: "Answered",
  declined: "Not answered",
  rejected: "Query rejected",
  failed: "Failed",
};

const DECLINE_TEXT: Record<string, string> = {
  personal_data: "This needs personal data, which is not available.",
  not_allowed: "This asks for something the analyst may not do.",
  not_in_data: "The data cannot answer this question.",
  unclear: "The question needs to be clearer.",
  refused: "The model declined this question.",
};

export function AnalysisView({ analysis }: { analysis: Analysis }) {
  const { insight, result } = analysis;
  return (
    <div className="space-y-6">
      <section className="card space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="badge">{STATUS_TEXT[analysis.status]}</span>
          {insight?.status === "verified" && (
            <span className="badge border-emerald-400 text-emerald-700 dark:text-emerald-300">
              {insight.numbers_checked} figures checked against the result
            </span>
          )}
          {insight?.status === "fallback" && (
            <span className="badge border-amber-400 text-amber-700 dark:text-amber-300">
              Commentary withheld: unverified figures
            </span>
          )}
          {analysis.masked_personal_data.length > 0 && (
            <span className="badge border-sky-400 text-sky-700 dark:text-sky-300">
              Masked in your question: {analysis.masked_personal_data.join(", ")}
            </span>
          )}
        </div>
        <p className="text-sm text-muted">{analysis.question}</p>

        {analysis.status === "declined" && (
          <div>
            <p className="font-medium">
              {DECLINE_TEXT[analysis.declined_reason ?? ""] ?? "Not answered."}
            </p>
            {analysis.error && <p className="mt-1 text-sm text-muted">{analysis.error}</p>}
          </div>
        )}
        {(analysis.status === "failed" || analysis.status === "rejected") && (
          <p className="text-sm">{analysis.error ?? "The analysis did not complete."}</p>
        )}

        {insight && (
          <div className="space-y-2">
            <p className="text-lg leading-relaxed">{insight.summary}</p>
            {insight.key_points.length > 0 && (
              <ul className="list-disc space-y-1 pl-5">
                {insight.key_points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            )}
            {insight.caveats.length > 0 && (
              <ul className="space-y-1 text-sm text-muted">
                {insight.caveats.map((caveat) => (
                  <li key={caveat}>⚠ {caveat}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {result && result.rows.length > 0 && (
        <>
          <ResultChart result={result} />
          <ResultTable result={result} />
        </>
      )}

      <AnalysisTrace analysis={analysis} />
    </div>
  );
}
