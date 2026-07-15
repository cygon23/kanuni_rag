import type { DocumentSummary } from "@kanuni/shared";

import { apiHeaders, apiUrl } from "@/lib/serverConfig";

async function fetchDocumentCount(): Promise<number | null> {
  try {
    const response = await fetch(apiUrl("/v1/documents?limit=200"), {
      headers: apiHeaders(),
      cache: "no-store",
    });
    if (!response.ok) return null;
    const documents = (await response.json()) as DocumentSummary[];
    return documents.length;
  } catch {
    return null;
  }
}

export default async function AboutPage() {
  const documentCount = await fetchDocumentCount();

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">About Kanuni</h1>

      <section className="mt-6 space-y-3 text-[15px] leading-relaxed text-neutral-800 dark:text-neutral-200">
        <p>
          Kanuni answers questions about Bank of Tanzania regulatory documents — banking licensing,
          capital adequacy, electronic money, foreign exchange, and related circulars — by
          retrieving the exact source text and citing it, rather than answering from a language
          model&apos;s general training.
        </p>
        <p>
          Every answer is grounded in retrieved chunks of the actual regulatory text. Citations link
          back to the specific document, section, and page. When nothing retrieved is a confident
          match, Kanuni refuses rather than guessing.
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Corpus coverage</h2>
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
          {documentCount !== null
            ? `${documentCount} document${documentCount === 1 ? "" : "s"} currently indexed.`
            : "Document count is unavailable right now."}{" "}
          See the{" "}
          <a href="/documents" className="underline">
            Documents
          </a>{" "}
          page for the full registry, including each document&apos;s status (in force, superseded,
          or repealed) and reference number.
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Limitations</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-neutral-600 dark:text-neutral-400">
          <li>
            Coverage is limited to whatever has been ingested into the corpus — Kanuni cannot answer
            questions about regulations, institutions, or jurisdictions outside it, and will refuse
            rather than fabricate an answer.
          </li>
          <li>
            Retrieval and generation are automated and can make mistakes: a low-confidence banner or
            a refusal both mean the same thing — verify against the cited source before relying on
            the answer.
          </li>
          <li>
            Point-in-time accuracy depends on the corpus being kept current; an amendment not yet
            ingested won&apos;t be reflected in an answer about the document it amends.
          </li>
        </ul>
      </section>

      <section className="mt-8 rounded-lg border border-neutral-300 bg-neutral-50 px-4 py-3 text-sm text-neutral-700 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
        <p>
          <strong className="font-semibold">Not legal advice.</strong> Kanuni is an information
          retrieval tool, not a substitute for professional legal or regulatory advice. For
          decisions with legal or financial consequences, consult a qualified professional and
          verify against the primary source.
        </p>
      </section>
    </div>
  );
}
