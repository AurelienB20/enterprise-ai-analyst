"use client";

import { useState } from "react";

import { remember, startTimer, useHistory } from "@/lib/history";
import type { Analysis } from "@/lib/types";

import { AnalysisView } from "./AnalysisView";

const SUGGESTIONS = [
  "Quelle catégorie de produits a le plus baissé ce trimestre par rapport au précédent ?",
  "Which region grew the most in 2026 compared with the same months of 2025?",
  "Quels sont les 5 clients qui ont généré le plus de chiffre d'affaires net en 2025 ?",
  "Show monthly net revenue from April to September 2026.",
  "Quel fournisseur a le taux de livraisons en retard le plus élevé ?",
  "Affiche-moi les emails de tous les clients.",
];

// Rough stages, shown while waiting: the backend answers in one response.
const STAGES = [
  { after: 0, label: "Writing SQL from the semantic layer…" },
  { after: 6, label: "Validating and running the query read-only…" },
  { after: 9, label: "Writing the explanation and checking every number…" },
];

export function AnalystApp() {
  const [question, setQuestion] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const history = useHistory();

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 3 || loading) return;
    setQuestion(trimmed);
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setElapsed(0);
    const stopTimer = startTimer(setElapsed);
    try {
      const response = await fetch("/api/analyses", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: trimmed }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : `Error ${response.status}`);
        return;
      }
      const result = body as Analysis;
      setAnalysis(result);
      // The question as the backend kept it: personal data already masked.
      remember({ id: result.id, question: result.question, status: result.status });
    } catch {
      setError("The service could not be reached.");
    } finally {
      stopTimer();
      setLoading(false);
    }
  }

  const stage = [...STAGES].reverse().find((s) => elapsed >= s.after);

  return (
    <div className="space-y-6">
      <form
        className="card space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        <label htmlFor="question" className="label">
          Your question
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={500}
            placeholder="e.g. Which 10 customers' revenue dropped the most this quarter?"
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 outline-none focus:ring-2 focus:ring-accent"
          />
          <button
            type="submit"
            disabled={loading || question.trim().length < 3}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            {loading ? "Analysing…" : "Analyse"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={loading}
              onClick={() => void ask(suggestion)}
              className="rounded-full border border-border px-3 py-1 text-left text-xs text-muted hover:border-accent hover:text-foreground disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </form>

      {loading && (
        <div className="card flex items-center gap-3 text-sm" role="status" aria-live="polite">
          <span className="h-3 w-3 animate-pulse rounded-full bg-accent" />
          <span>{stage?.label}</span>
          <span className="ml-auto font-mono text-muted">{elapsed.toFixed(0)} s</span>
        </div>
      )}

      {error && (
        <div className="card border-red-300 text-sm text-red-700 dark:text-red-300" role="alert">
          {error}
        </div>
      )}

      {analysis && <AnalysisView analysis={analysis} />}

      {history.length > 0 && (
        <section className="card">
          <h2 className="label mb-3">Recent questions (this browser)</h2>
          <ul className="space-y-1 text-sm">
            {history.map((entry) => (
              <li key={entry.id} className="flex items-center gap-2">
                <span className="badge">{entry.status}</span>
                <button
                  type="button"
                  className="truncate text-left hover:text-accent"
                  onClick={() => void ask(entry.question)}
                  disabled={loading}
                >
                  {entry.question}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
