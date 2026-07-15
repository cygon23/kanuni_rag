import type { ResolvedCitation } from "@kanuni/shared";

export function CitationChip({
  index,
  citation,
  onOpen,
}: {
  index: number;
  citation: ResolvedCitation | undefined;
  onOpen: () => void;
}) {
  if (!citation) {
    return (
      <span
        aria-hidden="true"
        className="mx-0.5 inline-block rounded px-1 text-xs text-neutral-400 dark:text-neutral-600"
      >
        [{index}]
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Citation ${index}: ${citation.document_title}${
        citation.section_ref ? `, ${citation.section_ref}` : ""
      }. Open source text.`}
      className="mx-0.5 inline-flex items-center rounded bg-blue-100 px-1.5 py-0.5 align-super text-xs font-medium text-blue-800 hover:bg-blue-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-blue-600 dark:bg-blue-950 dark:text-blue-300 dark:hover:bg-blue-900"
    >
      {index}
    </button>
  );
}
