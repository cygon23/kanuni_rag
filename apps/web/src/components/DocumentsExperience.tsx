"use client";

import type { DocumentStatus, DocumentSummary, DocumentType } from "@kanuni/shared";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorState } from "./ErrorState";

const STATUS_OPTIONS: { value: DocumentStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "in_force", label: "In force" },
  { value: "superseded", label: "Superseded" },
  { value: "repealed", label: "Repealed" },
  { value: "unknown", label: "Unknown" },
];

const TYPE_OPTIONS: { value: DocumentType | ""; label: string }[] = [
  { value: "", label: "All types" },
  { value: "act", label: "Act" },
  { value: "regulation", label: "Regulation" },
  { value: "circular", label: "Circular" },
  { value: "notice", label: "Notice" },
  { value: "guideline", label: "Guideline" },
];

const STATUS_BADGE: Record<DocumentStatus, string> = {
  in_force: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  superseded: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  repealed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  unknown: "bg-neutral-100 text-neutral-700 dark:bg-neutral-900 dark:text-neutral-400",
};

export function DocumentsExperience() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const status = (searchParams.get("status") ?? "") as DocumentStatus | "";
  const docType = (searchParams.get("doc_type") ?? "") as DocumentType | "";

  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    // Nested rather than inlined: keeps the effect body itself to just
    // "start an async task, clean up on unmount," which is what the
    // fetch-in-effect pattern React's docs recommend actually looks like
    // (https://react.dev/learn/you-might-not-need-an-effect#fetching-data)
    // — every setState call here happens after an await, in response to
    // the fetch settling, never synchronously as the effect runs.
    async function load() {
      setLoading(true);
      const query = new URLSearchParams();
      if (status) query.set("status", status);
      if (docType) query.set("doc_type", docType);

      try {
        const response = await fetch(`/api/documents?${query.toString()}`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
        const data = (await response.json()) as DocumentSummary[];
        setDocuments(data);
        setError(null);
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(caught);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    void load();
    return () => controller.abort();
  }, [status, docType]);

  function updateFilter(key: "status" | "doc_type", value: string) {
    const query = new URLSearchParams(searchParams.toString());
    if (value) {
      query.set(key, value);
    } else {
      query.delete(key);
    }
    router.replace(`/documents?${query.toString()}`);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
      <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
        The full registry of regulatory documents Kanuni has indexed.
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        <label className="text-sm">
          <span className="sr-only">Filter by status</span>
          <select
            value={status}
            onChange={(event) => updateFilter("status", event.target.value)}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="sr-only">Filter by document type</span>
          <select
            value={docType}
            onChange={(event) => updateFilter("doc_type", event.target.value)}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          >
            {TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-6">
        {error !== null && <ErrorState error={error} onRetry={() => router.refresh()} />}

        {error === null && loading && (
          <div aria-hidden="true" className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-12 w-full animate-pulse rounded bg-neutral-200 dark:bg-neutral-800"
              />
            ))}
          </div>
        )}

        {!error && !loading && documents && documents.length === 0 && (
          <p className="rounded-lg border border-dashed border-neutral-300 px-4 py-8 text-center text-sm text-neutral-500 dark:border-neutral-700">
            No documents match these filters.
          </p>
        )}

        {!error && !loading && documents && documents.length > 0 && (
          <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {documents.map((document) => (
              <li key={document.id} className="flex items-start justify-between gap-4 py-4">
                <div>
                  <p className="font-medium text-neutral-900 dark:text-neutral-100">
                    {document.title}
                  </p>
                  <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-500">
                    {document.reference_number ?? "No reference number"} · {document.language} ·{" "}
                    {document.doc_type}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_BADGE[document.status]}`}
                >
                  {document.status.replace("_", " ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
