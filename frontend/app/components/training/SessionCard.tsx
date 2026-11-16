"use client";

import Link from "next/link";
import { useId, useState } from "react";

import { SessionEditor } from "@/app/components/training/SessionEditor";
import { Badge, Button } from "@/app/components/ui";
import {
  basisLabel,
  basisNote,
  basisTone,
  evidenceLabel,
  formatDay,
  isConflict,
  localIso,
  sessionMeta,
  sourceLabel,
  statusLabel,
  statusTone,
  toDraftItems,
  type Activity,
  type PlanItem,
  type TrainingSession,
} from "@/app/lib/training";
import {
  completeSession,
  deleteSession,
  updateSession,
} from "@/app/lib/trainingApi";

type Video = { id: string; file_name: string; recorded_at: string };

// One activity with how it got into the session. Recommended, changed and added activities
// are never shown alike, and what the swimmer typed in is never called a recommendation.
export function ActivityRow({ item, showDone }: { item: PlanItem; showDone?: boolean }) {
  return (
    <li className="rounded-xl bg-slate-50 px-3 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-sm font-medium text-slate-900">
          {showDone && (
            <span className="mr-1.5 text-slate-500" aria-hidden="true">
              {item.done ? "✓" : "–"}
            </span>
          )}
          {item.name}
          {showDone && <span className="sr-only">{item.done ? " (done)" : " (not done)"}</span>}
        </p>
        <p className="text-sm text-slate-600 tabular-nums">
          {item.minutes} min{item.sets ? ` · ${item.sets}` : ""}
        </p>
      </div>
      <p className="mt-1 flex flex-wrap gap-x-2 text-xs text-slate-500">
        <span>{sourceLabel(item.source)}</span>
        {item.source !== "manual" && item.basis && <span>· {basisLabel(item.basis)}</span>}
        {item.activity_id && item.evidence_class && (
          <span>· {evidenceLabel(item.evidence_class)}</span>
        )}
        {item.intensity && <span>· {item.intensity}</span>}
      </p>
      {item.instructions.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-xs font-medium text-sky-700">
            How to do it
          </summary>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {item.instructions.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {item.rest && <p className="mt-1.5 text-sm text-slate-600">Rest: {item.rest}</p>}
          {item.equipment.length > 0 && (
            <p className="mt-1 text-sm text-slate-600">
              Needs: {item.equipment.map((e) => e.replace("_", " ")).join(", ")}
            </p>
          )}
        </details>
      )}
    </li>
  );
}

// A stored session with everything the swimmer can do to it. `onChanged` reloads the page's
// data after any change; nothing here updates a session without the swimmer asking.
export function SessionCard({
  session,
  library,
  videos = [],
  onChanged,
}: {
  session: TrainingSession;
  library: Activity[];
  videos?: Video[];
  onChanged: () => void;
}) {
  const id = useId();
  const [mode, setMode] = useState<"view" | "edit" | "complete" | "delete">("view");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<number[]>(session.items.map((_, i) => i));
  const [note, setNote] = useState("");
  const [on, setOn] = useState(localIso(new Date()));
  const [video, setVideo] = useState("");

  async function run(
    call: () => Promise<{ ok: boolean; error?: string; status?: number }>,
  ) {
    setBusy(true);
    setError(null);
    const res = await call();
    setBusy(false);
    if (res.ok) {
      setMode("view");
      onChanged();
    } else {
      setError(res.error ?? "That did not work.");
      // Changed in another tab or on another device: show what is stored now.
      if (isConflict(res.status ?? 0)) onChanged();
    }
  }

  const completed = session.status === "completed";
  const open = session.status === "planned";
  return (
    <article className="rounded-2xl border border-slate-200 bg-surface p-4" aria-labelledby={id}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-slate-500">
            {formatDay(session.date)}
            {session.time ? ` · ${session.time}` : ""}
          </p>
          <h3 id={id} className="mt-0.5 font-semibold text-slate-900">
            {session.title}
          </h3>
          <p className="mt-0.5 text-sm text-slate-600">{sessionMeta(session)}</p>
          {session.planned_date && session.planned_date !== session.date && (
            <p className="mt-0.5 text-xs text-slate-500">
              Moved by you from {formatDay(session.planned_date)}. A new plan will not add
              another session on that day.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={statusTone(session.status)}>{statusLabel(session.status)}</Badge>
          <Badge tone={basisTone(session.basis)}>{basisLabel(session.basis)}</Badge>
          {session.edited && session.origin === "generated" && (
            <Badge tone="slate">Edited by you</Badge>
          )}
        </div>
      </div>
      {session.objective && <p className="mt-2 text-sm text-slate-700">{session.objective}</p>}
      {session.explained && (
        <p className="mt-2 rounded-xl bg-sky-50 px-3 py-2 text-sm text-slate-700">
          {session.explained}{" "}
          <span className="text-xs text-slate-500">(Reworded by a language model.)</span>
        </p>
      )}
      <p className="mt-1 text-xs text-slate-500">{basisNote(session.basis)}</p>

      {mode === "edit" ? (
        <div className="mt-4">
          <SessionEditor
            initial={{
              date: session.date,
              time: session.time,
              title: session.title,
              items: toDraftItems(session.items),
            }}
            library={library}
            submitLabel="Save changes"
            onCancel={() => setMode("view")}
            onSubmit={async (draft) => {
              const res = await updateSession(session.id, session.revision, draft);
              if (!res.ok) {
                if (isConflict(res.status)) {
                  setMode("view");
                  setError(res.error);
                  onChanged();
                  return null;
                }
                return res.error;
              }
              setMode("view");
              onChanged();
              return null;
            }}
          />
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {session.items.map((item, i) => (
            <ActivityRow key={`${item.activity_id}-${item.name}-${i}`} item={item} showDone={completed} />
          ))}
        </ul>
      )}

      {session.checkpoint && mode === "view" && (
        <div className="mt-3 rounded-xl border border-dashed border-slate-300 px-3 py-2.5 text-sm">
          <p className="font-medium text-slate-900">{session.checkpoint.title}</p>
          <p className="mt-0.5 text-slate-700">{session.checkpoint.what_to_film}</p>
          <p className="mt-0.5 text-xs text-slate-500">{session.checkpoint.note}</p>
          <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
            <Link href="/analyze" className="font-medium text-sky-700 hover:text-sky-900">
              Upload a clip
            </Link>
            {session.checkpoint.source_video_id && (
              <Link
                href={`/history/${session.checkpoint.source_video_id}`}
                className="font-medium text-sky-700 hover:text-sky-900"
              >
                See the analysis it comes from
              </Link>
            )}
          </p>
        </div>
      )}

      {completed && session.completion && (
        <div className="mt-3 rounded-xl bg-teal-50 px-3 py-2.5 text-sm text-slate-700">
          <p>
            You marked this completed on {formatDay(session.completion.completed_on)}.
          </p>
          {session.completion.note && (
            <p className="mt-1">
              <span className="font-medium">Your note:</span> {session.completion.note}
            </p>
          )}
          {session.linked_video_id && (
            <Link
              href={`/history/${session.linked_video_id}`}
              className="mt-1 inline-block font-medium text-sky-700 hover:text-sky-900"
            >
              Linked video
            </Link>
          )}
          {session.linked_video_removed && (
            <p className="mt-1 text-xs text-slate-500">
              The video linked to this session has been deleted.
            </p>
          )}
        </div>
      )}

      {session.safety.length > 0 && mode === "view" && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-slate-600">
            Safety and rest
          </summary>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-slate-600">
            {session.rest_guidance && <li>{session.rest_guidance}</li>}
            {session.safety.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
      )}

      {mode === "complete" && (
        <form
          className="mt-4 space-y-3 rounded-xl bg-slate-50 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            run(() =>
              completeSession(session.id, {
                revision: session.revision,
                completed_on: on,
                done,
                note,
                video_id: video,
              }),
            );
          }}
        >
          <fieldset>
            <legend className="text-sm font-medium text-slate-700">What did you do?</legend>
            <ul className="mt-1.5 space-y-1">
              {session.items.map((item, i) => (
                <li key={`${item.name}-${i}`}>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-sky-700"
                      checked={done.includes(i)}
                      onChange={(e) =>
                        setDone(e.target.checked ? [...done, i] : done.filter((x) => x !== i))
                      }
                    />
                    {item.name} ({item.minutes} min)
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium text-slate-700">
              Date you swam
              <input
                type="date"
                value={on}
                onChange={(e) => setOn(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm"
              />
            </label>
            {videos.length > 0 && (
              <label className="block text-sm font-medium text-slate-700">
                Link one of your videos <span className="font-normal text-slate-500">(optional)</span>
                <select
                  value={video}
                  onChange={(e) => setVideo(e.target.value)}
                  className="mt-1 block w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm"
                >
                  <option value="">No video</option>
                  {videos.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.file_name || "Video"} ({v.recorded_at.slice(0, 10)})
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <label className="block text-sm font-medium text-slate-700">
            Note <span className="font-normal text-slate-500">(optional, only you see it)</span>
            <textarea
              value={note}
              maxLength={300}
              rows={2}
              onChange={(e) => setNote(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save as completed"}
            </Button>
            <Button variant="secondary" onClick={() => setMode("view")} disabled={busy}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {mode === "view" && (
        <div className="mt-4 flex flex-wrap gap-2">
          {open && <Button onClick={() => setMode("complete")}>Mark completed</Button>}
          {open && (
            <Button variant="secondary" onClick={() => setMode("edit")}>
              Edit or reschedule
            </Button>
          )}
          {open && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() =>
                run(() => updateSession(session.id, session.revision, { status: "skipped" }))
              }
            >
              Skip
            </Button>
          )}
          {open && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() =>
                run(() => updateSession(session.id, session.revision, { status: "canceled" }))
              }
            >
              Cancel session
            </Button>
          )}
          {!open && session.status !== "replaced" && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() =>
                run(() => updateSession(session.id, session.revision, { status: "planned" }))
              }
            >
              {completed ? "Undo completion" : "Plan it again"}
            </Button>
          )}
          <button
            type="button"
            onClick={() => setMode("delete")}
            className="rounded-lg px-3 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100"
          >
            Delete…
          </button>
        </div>
      )}
      {mode === "delete" && (
        <div className="mt-4 rounded-xl border border-slate-200 p-3" role="group" aria-label="Confirm deleting this session">
          <p className="text-sm text-slate-700">
            Delete this training session? Your videos and analyses are not affected.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => deleteSession(session.id, session.revision))}
              className="rounded-lg bg-red-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-800 disabled:opacity-60"
            >
              {busy ? "Deleting…" : "Yes, delete the session"}
            </button>
            <Button variant="secondary" onClick={() => setMode("view")} disabled={busy}>
              Keep it
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}
