// Reading server-sent events from a fetch response body (EventSource cannot POST).

export interface ServerEvent {
  event: string;
  data: string;
}

/** Split complete events out of ``buffer``; returns them and what is left over. */
export function parseEvents(buffer: string): { events: ServerEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: ServerEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length > 0) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

/** Calls ``onEvent`` for each event of the streamed response, as it arrives. */
export async function readEvents(
  response: Response,
  onEvent: (event: ServerEvent) => void,
): Promise<void> {
  if (!response.body) return;
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseEvents(buffer + value);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  parseEvents(buffer + "\n\n").events.forEach(onEvent);
}
