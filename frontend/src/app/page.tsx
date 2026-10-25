import Link from "next/link";

import { AnalystApp } from "@/components/AnalystApp";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-6">
      <header className="mb-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-3xl font-semibold tracking-tight">Enterprise AI Analyst</h1>
          <Link href="/metrics" className="text-sm text-muted hover:text-accent">
            Metrics
          </Link>
        </div>
        <p className="mt-2 text-muted">
          Ask questions about your business data. Get trusted insights, secure SQL and
          interactive visualizations.
        </p>
        <p className="mt-3 text-xs text-muted">
          Synthetic company data. Every query is validated and runs read-only; every figure
          in the commentary is checked against the result.
        </p>
      </header>
      <AnalystApp />
    </main>
  );
}
