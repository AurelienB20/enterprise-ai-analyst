import "server-only";

// Server-side calls from the Next.js Route Handlers to the FastAPI backend.
//
// The browser never talks to FastAPI: the API key stays on this server and there is no
// CORS to configure. Only the routes this interface needs are forwarded.

export const MAX_BODY_BYTES = 8 * 1024;
// An analysis with its explanation takes up to ~40 s with Claude Opus.
const TIMEOUT_MS = 120_000;

export interface BackendConfig {
  url: string;
  apiKey: string | undefined;
}

export function backendConfig(): BackendConfig {
  return {
    url: (process.env.API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, ""),
    apiKey: process.env.API_KEY || undefined,
  };
}

/**
 * The visitor's address, forwarded so the API limits each visitor rather than this
 * server: the last X-Forwarded-For entry, written by the nearest proxy (Caddy).
 */
export function clientAddress(headers: Headers): string | undefined {
  const entries = (headers.get("x-forwarded-for") ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  return entries.at(-1);
}

function jsonError(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

/** Forward ``request`` to ``path`` on the backend and return its response as is. */
export async function forward(
  request: Request,
  path: string,
  config: BackendConfig = backendConfig(),
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  let body: string | undefined;
  if (request.method !== "GET") {
    body = await request.text();
    if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
      return jsonError(413, "Request body too large.");
    }
  }
  const headers = new Headers({ accept: "application/json" });
  if (body !== undefined) headers.set("content-type", "application/json");
  if (config.apiKey) headers.set("x-api-key", config.apiKey);
  const client = clientAddress(request.headers);
  if (client) headers.set("x-forwarded-for", client);

  let response: Response;
  try {
    response = await fetchImpl(`${config.url}${path}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(TIMEOUT_MS)]),
    });
  } catch {
    return jsonError(502, "The backend is unreachable.");
  }
  const passed = new Headers({
    "content-type": response.headers.get("content-type") ?? "application/json",
  });
  for (const name of ["x-request-id", "retry-after"]) {
    const value = response.headers.get(name);
    if (value) passed.set(name, value);
  }
  return new Response(await response.text(), { status: response.status, headers: passed });
}

/**
 * Like ``forward``, for the streamed analysis: the server-sent events are passed on as
 * they arrive, never buffered, and the backend request stops if the browser leaves.
 */
export async function forwardStream(
  request: Request,
  path: string,
  config: BackendConfig = backendConfig(),
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  const body = await request.text();
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
    return jsonError(413, "Request body too large.");
  }
  const headers = new Headers({ accept: "text/event-stream", "content-type": "application/json" });
  if (config.apiKey) headers.set("x-api-key", config.apiKey);
  const client = clientAddress(request.headers);
  if (client) headers.set("x-forwarded-for", client);
  let response: Response;
  try {
    response = await fetchImpl(`${config.url}${path}`, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(TIMEOUT_MS)]),
    });
  } catch {
    return jsonError(502, "The backend is unreachable.");
  }
  const contentType = response.headers.get("content-type") ?? "application/json";
  if (!response.ok || !contentType.startsWith("text/event-stream")) {
    // Limits (429, 503) come back as JSON, with their Retry-After.
    const headers = new Headers({ "content-type": contentType });
    const retryAfter = response.headers.get("retry-after");
    if (retryAfter) headers.set("retry-after", retryAfter);
    return new Response(await response.text(), { status: response.status, headers });
  }
  return new Response(response.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
    },
  });
}

/** Read a JSON resource from the backend, server-side (for server components). */
export async function getJson<T>(path: string, config: BackendConfig = backendConfig()): Promise<T | null> {
  const headers = new Headers({ accept: "application/json" });
  if (config.apiKey) headers.set("x-api-key", config.apiKey);
  try {
    const response = await fetch(`${config.url}${path}`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return response.ok ? ((await response.json()) as T) : null;
  } catch {
    return null;
  }
}
