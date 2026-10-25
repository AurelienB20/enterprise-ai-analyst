import { describe, expect, it } from "vitest";

import { parseEvents, readEvents } from "./sse";

describe("parseEvents", () => {
  it("splits complete events and keeps the partial one", () => {
    const { events, rest } = parseEvents(
      'event: answer\ndata: {"a":1}\n\nevent: done\ndata: {"b"',
    );
    expect(events).toEqual([{ event: "answer", data: '{"a":1}' }]);
    expect(rest).toBe('event: done\ndata: {"b"');
  });

  it("accepts CRLF and multi-line data", () => {
    const { events } = parseEvents("event: x\r\ndata: one\r\ndata: two\r\n\r\n");
    expect(events).toEqual([{ event: "x", data: "one\ntwo" }]);
  });
});

describe("readEvents", () => {
  it("delivers events split across chunks, in order", async () => {
    const chunks = ['event: answer\ndata: {"id"', ':"1"}\n\nevent: done\n', 'data: {"id":"1"}\n\n'];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
        controller.close();
      },
    });
    const seen: string[] = [];

    await readEvents(new Response(stream), (event) => seen.push(`${event.event}:${event.data}`));

    expect(seen).toEqual(['answer:{"id":"1"}', 'done:{"id":"1"}']);
  });
});
