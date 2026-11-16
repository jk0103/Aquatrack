"use client";

import { useId, useState } from "react";

import { Button } from "@/app/components/ui";
import {
  addActivity,
  addCustom,
  checkDraftSession,
  draftMinutes,
  removeItem,
  setMinutes,
  type Activity,
  type DraftItem,
} from "@/app/lib/training";

export type SessionDraft = {
  date: string;
  time: string;
  title: string;
  items: DraftItem[];
};

const input =
  "block w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-sky-600 focus:ring-4 focus:ring-sky-600/15 focus:outline-none";

// Edit or create a session: when, what it is called, and which activities for how long.
// Library activities keep their instructions; anything the swimmer types in is theirs and
// is labelled that way everywhere.
export function SessionEditor({
  initial,
  library,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: SessionDraft;
  library: Activity[];
  submitLabel: string;
  onSubmit: (draft: SessionDraft) => Promise<string | null>;
  onCancel: () => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState(initial);
  const [pick, setPick] = useState("");
  const [own, setOwn] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const setItems = (items: DraftItem[]) => setDraft((d) => ({ ...d, items }));
  const total = draftMinutes(draft.items);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const problem = checkDraftSession(draft, library);
    if (problem) return setError(problem);
    setBusy(true);
    setError(await onSubmit({ ...draft, title: draft.title.trim() }));
    setBusy(false);
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="grid gap-3 sm:grid-cols-[1fr_9rem_8rem]">
        <label className="block text-sm font-medium text-slate-700" htmlFor={`${id}-title`}>
          Title
          <input
            id={`${id}-title`}
            className={`${input} mt-1`}
            value={draft.title}
            maxLength={80}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700" htmlFor={`${id}-date`}>
          Date
          <input
            id={`${id}-date`}
            type="date"
            className={`${input} mt-1`}
            value={draft.date}
            onChange={(e) => setDraft({ ...draft, date: e.target.value })}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700" htmlFor={`${id}-time`}>
          Time <span className="font-normal text-slate-500">(optional)</span>
          <input
            id={`${id}-time`}
            type="time"
            className={`${input} mt-1`}
            value={draft.time}
            onChange={(e) => setDraft({ ...draft, time: e.target.value })}
          />
        </label>
      </div>

      <fieldset>
        <legend className="text-sm font-medium text-slate-700">Activities</legend>
        {draft.items.length === 0 && (
          <p className="mt-1 text-sm text-slate-500">No activities yet. Add one below.</p>
        )}
        <ul className="mt-2 space-y-2">
          {draft.items.map((item, i) => {
            const known = library.find((a) => a.id === item.activity_id);
            return (
              <li
                key={`${item.activity_id}-${item.name}-${i}`}
                className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900">{item.name}</p>
                  <p className="text-xs text-slate-500">
                    {known
                      ? `${known.min_minutes}–${known.max_minutes} min`
                      : "Your own activity"}
                  </p>
                </div>
                <label className="flex items-center gap-1.5 text-sm text-slate-600">
                  <span className="sr-only">Minutes for {item.name}</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    min={known?.min_minutes ?? 1}
                    max={known?.max_minutes ?? 120}
                    className={`${input} w-20`}
                    value={Number.isFinite(item.minutes) ? item.minutes : ""}
                    onChange={(e) =>
                      setItems(setMinutes(draft.items, i, e.target.valueAsNumber))
                    }
                  />
                  min
                </label>
                <button
                  type="button"
                  onClick={() => setItems(removeItem(draft.items, i))}
                  className="rounded-lg px-2.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200"
                  aria-label={`Remove ${item.name}`}
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-sm text-slate-600">
          Total: <span className="font-semibold tabular-nums">{total || 0} min</span>
        </p>

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="flex gap-2">
            <label className="sr-only" htmlFor={`${id}-pick`}>
              Add an activity from the library
            </label>
            <select
              id={`${id}-pick`}
              className={input}
              value={pick}
              onChange={(e) => setPick(e.target.value)}
            >
              <option value="">Add from the library…</option>
              {library.map((a) => (
                <option
                  key={a.id}
                  value={a.id}
                  disabled={
                    a.not_offered !== null || draft.items.some((i) => i.activity_id === a.id)
                  }
                >
                  {a.name}
                  {a.not_offered ? " (not available: level or equipment)" : ""}
                </option>
              ))}
            </select>
            <Button
              variant="secondary"
              disabled={!pick}
              onClick={() => {
                const activity = library.find((a) => a.id === pick);
                if (activity) setItems(addActivity(draft.items, activity));
                setPick("");
              }}
            >
              Add
            </Button>
          </div>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor={`${id}-own`}>
              Add your own activity
            </label>
            <input
              id={`${id}-own`}
              className={input}
              placeholder="Or type your own activity"
              maxLength={60}
              value={own}
              onChange={(e) => setOwn(e.target.value)}
            />
            <Button
              variant="secondary"
              disabled={!own.trim()}
              onClick={() => {
                setItems(addCustom(draft.items, own));
                setOwn("");
              }}
            >
              Add
            </Button>
          </div>
        </div>
      </fieldset>

      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
