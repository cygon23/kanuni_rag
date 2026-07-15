import { apiHeaders, apiUrl, upstreamUnavailableResponse } from "@/lib/serverConfig";

// Proxies GET /v1/documents, forwarding filter/pagination query params as-is.
export async function GET(request: Request): Promise<Response> {
  const { search } = new URL(request.url);

  let upstream: Response;
  try {
    upstream = await fetch(apiUrl(`/v1/documents${search}`), {
      headers: apiHeaders(),
      cache: "no-store",
    });
  } catch (error) {
    return upstreamUnavailableResponse(error);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
