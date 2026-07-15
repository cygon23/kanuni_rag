export function ConfidenceBanner() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      <span aria-hidden="true" className="mt-0.5">
        ⚠️
      </span>
      <p>
        <strong className="font-semibold">Low confidence.</strong> The retrieved sources only weakly
        match this question — read the citations carefully before relying on this answer.
      </p>
    </div>
  );
}
