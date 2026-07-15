"use client";

import type { ResolvedCitation } from "@kanuni/shared";
import { useEffect, useRef } from "react";

const STATUS_LABEL: Record<ResolvedCitation["status"], string> = {
  in_force: "In force",
  superseded: "Superseded",
  repealed: "Repealed",
  unknown: "Status unknown",
};

export function ChunkSidePanel({
  citation,
  onClose,
}: {
  citation: ResolvedCitation;
  onClose: () => void;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const pageFragment = `#page=${citation.page_start}`;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close citation panel"
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="citation-panel-title"
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-neutral-200 bg-white p-6 shadow-xl dark:border-neutral-800 dark:bg-neutral-950"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="citation-panel-title" className="text-base font-semibold">
            {citation.document_title}
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md px-2 py-1 text-neutral-500 hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 dark:hover:bg-neutral-900"
          >
            ✕
          </button>
        </div>

        <dl className="mt-3 space-y-1 text-sm text-neutral-600 dark:text-neutral-400">
          {citation.reference_number && (
            <div className="flex gap-2">
              <dt className="font-medium">Reference:</dt>
              <dd>{citation.reference_number}</dd>
            </div>
          )}
          {citation.section_ref && (
            <div className="flex gap-2">
              <dt className="font-medium">Section:</dt>
              <dd>{citation.section_ref}</dd>
            </div>
          )}
          <div className="flex gap-2">
            <dt className="font-medium">Pages:</dt>
            <dd>
              {citation.page_start === citation.page_end
                ? citation.page_start
                : `${citation.page_start}–${citation.page_end}`}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="font-medium">Status:</dt>
            <dd>{STATUS_LABEL[citation.status]}</dd>
          </div>
        </dl>

        <blockquote className="mt-4 whitespace-pre-wrap rounded-md border border-neutral-200 bg-neutral-50 p-4 text-sm leading-relaxed text-neutral-800 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-200">
          {citation.content}
        </blockquote>

        {citation.source_url && (
          <a
            href={`${citation.source_url}${pageFragment}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-flex w-fit items-center gap-1 text-sm font-medium text-blue-700 hover:underline dark:text-blue-400"
          >
            Open source PDF ↗
          </a>
        )}
      </div>
    </div>
  );
}
