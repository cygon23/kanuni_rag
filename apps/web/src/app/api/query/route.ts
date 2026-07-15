import { apiHeaders, apiUrl, upstreamUnavailableResponse } from "@/lib/serverConfig";

// Proxies POST /v1/query, passing the upstream SSE stream straight
// through to the browser. See lib/serverConfig.ts for why this proxy
// exists (keeping KANUNI_API_KEY off the client) instead of the browser
// calling apps/api directly.
export async function POST(request: Request): Promise<Response> {
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(apiUrl("/v1/query"), {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body,
    });
  } catch (error) {
    return upstreamUnavailableResponse(error);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}
