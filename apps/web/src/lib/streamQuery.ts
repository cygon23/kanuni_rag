import type { ProblemDetails, QueryRequest, QueryStreamEvent } from "@kanuni/shared";

/** Thrown when `/api/query` (the apps/api proxy) responds with a non-2xx status. */
export class QueryRequestError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails | null;

  constructor(status: number, problem: ProblemDetails | null) {
    super(problem?.detail ?? `Query request failed with status ${status}`);
    this.name = "QueryRequestError";
    this.status = status;
    this.problem = problem;
  }
}

/**
 * Parses one SSE frame (the text between blank-line separators) into an
 * `event:`/`data:` pair. Multi-line `data:` fields are joined with `\n`,
 * per the SSE spec — `sse-starlette` only ever sends single-line `data:`
 * here (see `query_service.run_query`'s docstring on why `data` is
 * pre-serialized to a JSON string), but this handles the general case.
 */
function parseFrame(frame: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

function toQueryStreamEvent(frame: { event: string; data: string }): QueryStreamEvent | null {
  if (frame.event === "token") {
    return { event: "token", data: frame.data };
  }
  if (frame.event === "done") {
    return { event: "done", data: JSON.parse(frame.data) };
  }
  return null;
}

/**
 * POSTs a question to `/api/query` and yields parsed SSE events as they
 * arrive. A native `EventSource` can't be used here since it can't send a
 * POST body — this reads the streamed `Response` body directly instead.
 */
export async function* streamQuery(
  request: QueryRequest,
  signal?: AbortSignal,
): AsyncGenerator<QueryStreamEvent> {
  const response = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = (await response.json()) as ProblemDetails;
    } catch {
      // Non-JSON error body (e.g. a proxy/network-layer failure) — problem stays null.
    }
    throw new QueryRequestError(response.status, problem);
  }
  if (!response.body) {
    throw new QueryRequestError(response.status, null);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separatorIndex: number;
      while ((separatorIndex = buffer.search(/\r\n\r\n|\n\n|\r\r/)) !== -1) {
        const frameText = buffer.slice(0, separatorIndex);
        const separatorMatch = /\r\n\r\n|\n\n|\r\r/.exec(buffer.slice(separatorIndex));
        buffer = buffer.slice(separatorIndex + (separatorMatch?.[0].length ?? 2));

        const frame = parseFrame(frameText);
        if (frame) {
          const event = toQueryStreamEvent(frame);
          if (event) yield event;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
