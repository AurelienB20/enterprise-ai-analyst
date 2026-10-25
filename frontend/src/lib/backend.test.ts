import { describe, expect, it } from "vitest";

import { forward, MAX_BODY_BYTES } from "./backend";

const config = { url: "http://backend", apiKey: "secret-key" };

describe("forward", () => {
  it("adds the API key server-side and passes the answer back", async () => {
    let seen: { url: string; init: RequestInit } | undefined;
    const fakeFetch = (async (url: string, init: RequestInit) => {
      seen = { url, init };
      return new Response('{"status":"answered"}', {
        status: 200,
        headers: { "content-type": "application/json", "x-request-id": "req-1" },
      });
    }) as unknown as typeof fetch;

    const request = new Request("http://ui/api/analyses", {
      method: "POST",
      body: JSON.stringify({ question: "Revenue?" }),
      headers: { "x-api-key": "from-the-browser" },
    });
    const response = await forward(request, "/analyses", config, fakeFetch);

    expect(seen?.url).toBe("http://backend/analyses");
    expect(new Headers(seen?.init.headers).get("x-api-key")).toBe("secret-key");
    expect(response.status).toBe(200);
    expect(response.headers.get("x-request-id")).toBe("req-1");
    expect(await response.json()).toEqual({ status: "answered" });
  });

  it("refuses large bodies and reports an unreachable backend", async () => {
    const big = new Request("http://ui/api/analyses", {
      method: "POST",
      body: "x".repeat(MAX_BODY_BYTES + 1),
    });
    expect((await forward(big, "/analyses", config)).status).toBe(413);

    const failing = (async () => {
      throw new Error("connection refused");
    }) as unknown as typeof fetch;
    const request = new Request("http://ui/api/analyses", { method: "POST", body: "{}" });
    expect((await forward(request, "/analyses", config, failing)).status).toBe(502);
  });
});
