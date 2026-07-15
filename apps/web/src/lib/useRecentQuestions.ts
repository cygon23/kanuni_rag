"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "kanuni:recent-questions";
const MAX_RECENT = 10;

// A localStorage-backed external store, read via useSyncExternalStore
// (the correct primitive for subscribing to state that lives outside
// React — see https://react.dev/reference/react/useSyncExternalStore).
// Avoids the read-in-a-useEffect-then-setState pattern, which both
// causes an extra render and trips eslint-plugin-react-hooks'
// set-state-in-effect rule.
const EMPTY_SNAPSHOT: string[] = [];
const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedValue: string[] = EMPTY_SNAPSHOT;

function getSnapshot(): string[] {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      cachedValue = raw ? (JSON.parse(raw) as string[]) : EMPTY_SNAPSHOT;
    } catch {
      cachedValue = EMPTY_SNAPSHOT;
    }
  }
  return cachedValue;
}

function getServerSnapshot(): string[] {
  // Must return a referentially-stable value across calls (React compares
  // by reference) — a fresh `[]` literal here, even though "empty" every
  // time, reads as "changed" on every render and triggers React's
  // "getServerSnapshot should be cached" infinite-loop guard.
  return EMPTY_SNAPSHOT;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function persist(value: string[]): void {
  cachedValue = value;
  cachedRaw = JSON.stringify(value);
  try {
    window.localStorage.setItem(STORAGE_KEY, cachedRaw);
  } catch {
    // Storage full/unavailable — the in-memory cache (and this tab's
    // subscribers) still update for the rest of the session.
  }
  for (const listener of listeners) listener();
}

/**
 * Tracks recently-asked questions in `localStorage` only (§9: "local
 * only") — never sent to the API or logged anywhere server-side.
 */
export function useRecentQuestions(): {
  recentQuestions: string[];
  addRecentQuestion: (question: string) => void;
  clearRecentQuestions: () => void;
} {
  const recentQuestions = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const addRecentQuestion = useCallback((question: string) => {
    persist([question, ...getSnapshot().filter((q) => q !== question)].slice(0, MAX_RECENT));
  }, []);

  const clearRecentQuestions = useCallback(() => {
    persist([]);
  }, []);

  return { recentQuestions, addRecentQuestion, clearRecentQuestions };
}
