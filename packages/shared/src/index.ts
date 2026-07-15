// Re-exports the API's generated OpenAPI types under friendlier names, plus
// a small set of hand-maintained types for POST /v1/query's SSE payload —
// see the comment below `QueryResultMetadata` for why those aren't generated.
// Regenerate the OpenAPI-derived half with `make openapi`.

import type { components } from "./generated/api";

export type DocumentSummary = components["schemas"]["DocumentSummary"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type DocumentType = components["schemas"]["DocumentType"];
export type PipelineStage = components["schemas"]["PipelineStage"];
export type QueryRequest = components["schemas"]["QueryRequest"];

/**
 * Every error response's shape (RFC 7807 `application/problem+json`).
 * Also hand-maintained: `register_exception_handlers` builds this dict
 * directly rather than through a `response_model`
 * (`apps/api/src/kanuni_api/middleware/error_handler.py`), so it isn't in
 * the generated OpenAPI schema either.
 */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  error_code: string;
}

/**
 * `POST /v1/query`'s SSE stream isn't visible to FastAPI's OpenAPI schema
 * generator (the route returns a bare `EventSourceResponse`, not a
 * `response_model` FastAPI can introspect — see
 * `apps/api/src/kanuni_api/routes/query.py`), so these three mirror
 * `apps/api/src/kanuni_api/models/query.py` by hand. Keep them in sync
 * manually when that file changes.
 */
export type ConfidenceTier = "refuse" | "low" | "ok";

export interface ResolvedCitation {
  chunk_id: string;
  document_id: string;
  document_title: string;
  reference_number: string | null;
  section_ref: string | null;
  page_start: number;
  page_end: number;
  status: DocumentStatus;
  content: string;
  source_url: string | null;
}

export interface DocumentPointer {
  document_id: string;
  title: string;
  reference_number: string | null;
}

export interface QueryResultMetadata {
  confidence: ConfidenceTier;
  answered: boolean;
  citations: ResolvedCitation[];
  pointers: DocumentPointer[];
  prompt_tokens: number | null;
  completion_tokens: number | null;
  citation_density: number | null;
  latency_ms: number;
}

/** One parsed `POST /v1/query` SSE event, as consumed by `apps/web`'s Ask page. */
export type QueryStreamEvent =
  | { event: "token"; data: string }
  | { event: "done"; data: QueryResultMetadata };
