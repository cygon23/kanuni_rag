// Mirrors apps/api/src/kanuni_api/generation/citation.py's _CITATION_PATTERN —
// keep the two in sync if that pattern ever changes.
const CITATION_PATTERN = /\[chunk:([0-9a-fA-F-]{36})\]/g;

export type AnswerSegment = { type: "text"; value: string } | { type: "citation"; chunkId: string };

/** Splits streamed answer text into plain-text runs and citation markers, in order. */
export function splitAnswerIntoSegments(text: string): AnswerSegment[] {
  const segments: AnswerSegment[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(CITATION_PATTERN)) {
    const chunkId = match[1];
    if (!chunkId) continue;
    const index = match.index;
    if (index > lastIndex) {
      segments.push({ type: "text", value: text.slice(lastIndex, index) });
    }
    segments.push({ type: "citation", chunkId });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ type: "text", value: text.slice(lastIndex) });
  }
  return segments;
}
