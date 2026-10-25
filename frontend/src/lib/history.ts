"use client";

// Recent questions, kept in this browser only (localStorage): a convenience, never the
// record of what was asked (that is the backend's audit trail). Read through
// useSyncExternalStore, so the server render and the first client render agree.

import { useSyncExternalStore } from "react";

export interface HistoryEntry {
  id: string;
  question: string;
  status: string;
}

const KEY = "eaa.history";
const EVENT = "eaa-history";
const MAX_ENTRIES = 8;

function read(): string {
  try {
    return localStorage.getItem(KEY) ?? "[]";
  } catch {
    return "[]";
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

export function parseHistory(raw: string): HistoryEntry[] {
  try {
    const value: unknown = JSON.parse(raw);
    return Array.isArray(value) ? (value as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function useHistory(): HistoryEntry[] {
  const raw = useSyncExternalStore(subscribe, read, () => "[]");
  return parseHistory(raw);
}

export function remember(entry: HistoryEntry): void {
  const next = [entry, ...parseHistory(read()).filter((e) => e.question !== entry.question)];
  try {
    localStorage.setItem(KEY, JSON.stringify(next.slice(0, MAX_ENTRIES)));
    window.dispatchEvent(new Event(EVENT));
  } catch {
    // Without storage, history simply does not persist.
  }
}

/** Calls ``onTick`` with the seconds elapsed, until the returned function is called. */
export function startTimer(onTick: (seconds: number) => void): () => void {
  const started = Date.now();
  const id = setInterval(() => onTick((Date.now() - started) / 1000), 250);
  return () => clearInterval(id);
}
