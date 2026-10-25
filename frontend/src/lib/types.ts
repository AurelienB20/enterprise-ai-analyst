// The backend's AnalysisResponse (backend/src/eaa/api/analyses.py).

export type Status = "answered" | "declined" | "rejected" | "failed";

export interface Column {
  name: string;
  type: string;
  classification: "public" | "internal" | "confidential" | "pii" | null;
  sources: string[];
}

// Exact decimals travel as strings, dates as ISO strings.
export type Cell = string | number | boolean | null;

export interface Result {
  columns: Column[];
  rows: Cell[][];
  row_count: number;
  truncated: boolean;
}

export interface Insight {
  status: "verified" | "fallback" | "failed";
  summary: string;
  key_points: string[];
  caveats: string[];
  numbers_checked: number;
}

export interface Attempt {
  sql: string;
  outcome: "accepted" | "rejected" | "failed";
  message: string | null;
}

export interface Analysis {
  id: string;
  status: Status;
  question: string;
  model: string;
  explanation: string | null;
  assumptions: string[];
  ambiguities: string[];
  proposed_sql: string | null;
  executed_sql: string | null;
  views: string[];
  result: Result | null;
  insight: Insight | null;
  attempts: Attempt[];
  masked_personal_data: string[];
  declined_reason: string | null;
  error: string | null;
  timings: { generation_ms: number; execution_ms: number; explanation_ms: number; total_ms: number };
  usage: {
    llm_calls: number;
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens: number;
    cost_usd: number;
  };
}
