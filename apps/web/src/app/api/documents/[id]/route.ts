import { apiHeaders, apiUrl, upstreamUnavailableResponse } from "@/lib/serverConfig";

// Proxies GET /v1/documents/{id}.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;

  let upstream: Response;
  try {
    upstream = await fetch(apiUrl(`/v1/documents/${id}`), {
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
