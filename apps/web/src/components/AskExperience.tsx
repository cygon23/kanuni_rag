"use client";

import type { QueryResultMetadata, ResolvedCitation } from "@kanuni/shared";
import { useEffect, useMemo, useRef, useState } from "react";

import { splitAnswerIntoSegments } from "@/lib/citations";
import { streamQuery } from "@/lib/streamQuery";
import { useRecentQuestions } from "@/lib/useRecentQuestions";

import { ChunkSidePanel } from "./ChunkSidePanel";
import { CitationChip } from "./CitationChip";
import { ConfidenceBanner } from "./ConfidenceBanner";
import { ErrorState } from "./ErrorState";
import { RecentQuestions } from "./RecentQuestions";
import { RefusalState } from "./RefusalState";

type Status = "idle" | "streaming" | "done" | "error";

export function AskExperience() {
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [answerText, setAnswerText] = useState("");
  const [metadata, setMetadata] = useState<QueryResultMetadata | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [activeCitation, setActiveCitation] = useState<ResolvedCitation | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const { recentQuestions, addRecentQuestion, clearRecentQuestions } = useRecentQuestions();

  useEffect(() => () => abortControllerRef.current?.abort(), []);

  async function runQuery(submittedQuestion: string) {
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setStatus("streaming");
    setAnswerText("");
    setMetadata(null);
    setError(null);
    setActiveCitation(null);

    try {
      for await (const event of streamQuery(
        { question: submittedQuestion, include_historical: false, top_k: null },
        controller.signal,
      )) {
        if (event.event === "token") {
          setAnswerText((previous) => previous + event.data);
        } else {
          setMetadata(event.data);
          setStatus("done");
        }
      }
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(caught);
      setStatus("error");
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || status === "streaming") return;
    addRecentQuestion(trimmed);
    void runQuery(trimmed);
  }

  const citationsById = useMemo(() => {
    const map = new Map<string, ResolvedCitation>();
    for (const citation of metadata?.citations ?? []) map.set(citation.chunk_id, citation);
    return map;
  }, [metadata]);

  const segments = useMemo(() => splitAnswerIntoSegments(answerText), [answerText]);
  const citationOrder = useMemo(() => {
    const order: string[] = [];
    for (const segment of segments) {
      if (segment.type === "citation" && !order.includes(segment.chunkId)) {
        order.push(segment.chunkId);
      }
    }
    return order;
  }, [segments]);

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Ask Kanuni</h1>
      <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
        Ask a question about Bank of Tanzania regulations. Every answer is grounded in cited source
        text — Kanuni refuses rather than guesses when it isn&apos;t confident.
      </p>

      <form onSubmit={handleSubmit} className="mt-6">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSubmit(event);
            }
          }}
          placeholder="e.g. What is the minimum core capital for a commercial bank?"
          rows={3}
          className="w-full resize-none rounded-lg border border-neutral-300 bg-white px-4 py-3 text-sm shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 dark:border-neutral-700 dark:bg-neutral-900"
        />
        <div className="mt-2 flex justify-end">
          <button
            type="submit"
            disabled={status === "streaming" || question.trim().length === 0}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
          >
            {status === "streaming" ? "Asking…" : "Ask"}
          </button>
        </div>
      </form>

      <div className="mt-6 space-y-4" aria-live="polite">
        {status === "error" && (
          <ErrorState error={error} onRetry={() => void runQuery(question.trim())} />
        )}

        {status === "streaming" && answerText.length === 0 && (
          <div aria-hidden="true" className="space-y-2">
            <div className="h-3 w-full animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
            <div className="h-3 w-5/6 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
          </div>
        )}

        {status === "done" && metadata && !metadata.answered && (
          <RefusalState pointers={metadata.pointers} />
        )}

        {answerText.length > 0 && (status === "streaming" || (metadata?.answered ?? false)) && (
          <div className="space-y-3">
            {metadata?.confidence === "low" && <ConfidenceBanner />}
            <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-neutral-900 dark:text-neutral-100">
              {segments.map((segment, index) =>
                segment.type === "text" ? (
                  <span key={index}>{segment.value}</span>
                ) : (
                  <CitationChip
                    key={index}
                    index={citationOrder.indexOf(segment.chunkId) + 1}
                    citation={citationsById.get(segment.chunkId)}
                    onOpen={() => {
                      const citation = citationsById.get(segment.chunkId);
                      if (citation) setActiveCitation(citation);
                    }}
                  />
                ),
              )}
            </p>
          </div>
        )}
      </div>

      <RecentQuestions
        questions={recentQuestions}
        onSelect={(selected) => {
          setQuestion(selected);
          addRecentQuestion(selected);
          void runQuery(selected);
        }}
        onClear={clearRecentQuestions}
      />

      {activeCitation && (
        <ChunkSidePanel citation={activeCitation} onClose={() => setActiveCitation(null)} />
      )}
    </div>
  );
}
