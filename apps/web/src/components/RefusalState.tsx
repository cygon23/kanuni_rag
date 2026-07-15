import type { DocumentPointer } from "@kanuni/shared";

export function RefusalState({ pointers }: { pointers: DocumentPointer[] }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-neutral-300 bg-neutral-50 px-5 py-4 dark:border-neutral-700 dark:bg-neutral-900"
    >
      <p className="font-semibold text-neutral-900 dark:text-neutral-100">
        Kanuni can&apos;t answer this confidently.
      </p>
      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
        Either the corpus doesn&apos;t cover this topic, or nothing retrieved was a close enough
        match. Answering anyway risks giving you a wrong regulatory answer, so Kanuni doesn&apos;t
        guess.
      </p>
      {pointers.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            Closest documents in the corpus:
          </p>
          <ul className="mt-2 space-y-1">
            {pointers.map((pointer) => (
              <li key={pointer.document_id} className="text-sm">
                <span className="text-neutral-800 dark:text-neutral-200">{pointer.title}</span>
                {pointer.reference_number && (
                  <span className="text-neutral-500 dark:text-neutral-500">
                    {" "}
                    ({pointer.reference_number})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
