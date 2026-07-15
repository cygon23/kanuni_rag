import { QueryRequestError } from "@/lib/streamQuery";

function messageFor(error: unknown): { title: string; detail: string } {
  if (error instanceof QueryRequestError) {
    if (error.status === 401 || error.status === 403) {
      return {
        title: "Not authorized",
        detail:
          "The server rejected this request's API key. If you're running this yourself, check KANUNI_API_KEY in your .env.",
      };
    }
    if (error.status === 429) {
      return {
        title: "Rate-limited",
        detail: "Too many requests right now — wait a moment and try again.",
      };
    }
    if (error.status >= 500) {
      return {
        title: "Server error",
        detail: error.problem?.detail ?? "Something went wrong on the server. Please try again.",
      };
    }
    return {
      title: "Request failed",
      detail: error.problem?.detail ?? error.message,
    };
  }
  if (error instanceof Error && error.name === "AbortError") {
    return { title: "Cancelled", detail: "The request was cancelled." };
  }
  return {
    title: "Network error",
    detail: "Couldn't reach the server. Check your connection and try again.",
  };
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { title, detail } = messageFor(error);

  return (
    <div
      role="alert"
      className="rounded-lg border border-red-300 bg-red-50 px-5 py-4 dark:border-red-900 dark:bg-red-950"
    >
      <p className="font-semibold text-red-900 dark:text-red-200">{title}</p>
      <p className="mt-1 text-sm text-red-800 dark:text-red-300">{detail}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 rounded-md border border-red-400 px-3 py-1.5 text-sm font-medium text-red-900 hover:bg-red-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 dark:border-red-700 dark:text-red-200 dark:hover:bg-red-900"
      >
        Try again
      </button>
    </div>
  );
}
