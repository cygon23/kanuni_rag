// Server-only config for apps/web's proxy Route Handlers. Never imported
// from a Client Component — importing "server-only" makes that a build
// error instead of a silent leak of KANUNI_API_KEY into the client bundle.
import "server-only";

function requireApiBaseUrl(): string {
  return process.env.KANUNI_API_BASE_URL ?? "http://localhost:8000";
}

function requireApiKey(): string {
  const key = process.env.KANUNI_API_KEY;
  if (!key) {
    throw new Error(
      "KANUNI_API_KEY is not set. apps/web's proxy routes need a `query`-scoped Kanuni API key " +
        "— see .env.example's Phase 5 section.",
    );
  }
  return key;
}

export function apiUrl(path: string): string {
  return `${requireApiBaseUrl()}${path}`;
}

export function apiHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  headers.set("X-API-Key", requireApiKey());
  return headers;
}

/**
 * A well-formed JSON error response for when the upstream Kanuni API
 * can't be reached at all (connection refused/timeout) or `KANUNI_API_KEY`
 * isn't configured — as opposed to letting the exception propagate, which
 * Next.js turns into an opaque empty-bodied 500 that the frontend's error
 * states can't extract a message from.
 */
export function upstreamUnavailableResponse(error: unknown): Response {
  const detail = error instanceof Error ? error.message : "Unknown error";
  return Response.json(
    {
      type: "https://kanuni.dev/errors/upstream_unavailable",
      title: "UpstreamUnavailable",
      status: 502,
      detail: `Could not reach the Kanuni API: ${detail}`,
      instance: "",
      error_code: "upstream_unavailable",
    },
    { status: 502 },
  );
}
