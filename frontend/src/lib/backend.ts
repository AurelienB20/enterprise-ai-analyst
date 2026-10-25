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
  const requestId = response.headers.get("x-request-id");
  if (requestId) passed.set("x-request-id", requestId);
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
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": contentType },
    });
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
