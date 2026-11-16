"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useUser } from "@/app/components/AppShell";
import { ActivityRow, SessionCard } from "@/app/components/training/SessionCard";
import { TrainingPrefsForm } from "@/app/components/training/TrainingPrefsForm";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  LoadingState,
  PageHeader,
  Stat,
} from "@/app/components/ui";
import {
  formatMinutes,
  goalLabel,
  levelLabel,
  loadProfile,
  type Profile,
  type SwimLevel,
} from "@/app/lib/profile";
import {
  basisLabel,
  basisNote,
  basisTone,
  DAY_OPTIONS,
  evidenceLabel,
  formatDay,
  localIso,
  sessionMeta,
  statusLabel,
  statusTone,
  type SaveResult,
  type TrainingOverview,
  type TrainingPlan,
} from "@/app/lib/training";
import { fetchTraining, previewPlan, savePlan } from "@/app/lib/trainingApi";

type Conflict = Extract<SaveResult, { saved: false }>["conflict"];

export default function TrainingPage() {
  const user = useUser();
  const uid = user?.uid;
  const [view, setView] = useState<TrainingOverview | null>(null);
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [editingPrefs, setEditingPrefs] = useState(false);

  const reload = useCallback(() => {
    if (!uid) return;
    fetchTraining().then((res) => {
      if (res.ok) {
        setView(res.data);
        setError(null);
      } else setError(res.error);
    });
    loadProfile(uid)
      .then(setProfile)
      .catch(() => setProfile(null));
  }, [uid]);
  useEffect(reload, [reload]);

  return (
    <>
      <PageHeader
        title="Training"
        subtitle="Practice plans built from your goals and, where your analysis supports it, from your own swimming."
        action={<ButtonLink href="/calendar">Open calendar</ButtonLink>}
      />
      {error && (
        <p role="alert" className="mb-6 text-sm text-red-700">
          Couldn&apos;t load your training. {error}
        </p>
      )}
      {!view && !error && <LoadingState label="Loading your training…" />}
      {view && (
        <div className="space-y-6">
          <ThisWeek view={view} />

          <Card
            title="Your goals and preferences"
            action={
              profile && !editingPrefs ? (
                <Button variant="secondary" onClick={() => setEditingPrefs(true)}>
                  Edit preferences
                </Button>
              ) : undefined
            }
          >
            {profile === null ? (
              <p className="text-sm text-slate-600">
                Fill in your profile to set training preferences.{" "}
                <Link href="/profile" className="font-medium text-sky-700 hover:text-sky-900">
                  Go to your profile
                </Link>
                . Until then, plans use cautious general defaults.
              </p>
            ) : editingPrefs && profile && uid ? (
              <TrainingPrefsForm
                uid={uid}
                profile={profile}
                onCancel={() => setEditingPrefs(false)}
                onSaved={() => {
                  setEditingPrefs(false);
                  reload();
                }}
              />
            ) : (
              <Preferences view={view} />
            )}
          </Card>

          <Basis view={view} />
          <Generator view={view} onSaved={reload} />

          <section aria-labelledby="plans-heading" className="space-y-4">
            <h2 id="plans-heading" className="text-lg font-semibold text-slate-900">
              Your plans
            </h2>
            {view.plans.length === 0 ? (
              <Card>
                <p className="text-sm text-slate-600">
                  No saved plans yet. Make one above; you can review it before anything is
                  saved.
                </p>
              </Card>
            ) : (
              view.plans.map((plan) => (
                <SavedPlan key={plan.id} plan={plan} view={view} onChanged={reload} />
              ))
            )}
          </section>

          <History view={view} />
          <Library view={view} />
        </div>
      )}
    </>
  );
}

function ThisWeek({ view }: { view: TrainingOverview }) {
  const w = view.week;
  return (
    <Card title={`This week (${formatDay(w.start, { month: "short", day: "numeric" })} – ${formatDay(w.end, { month: "short", day: "numeric" })})`}>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Still planned" value={String(w.planned)} />
        <Stat label="Completed" value={String(w.completed)} />
        <Stat label="Skipped" value={String(w.skipped)} />
        <Stat label="Cancelled" value={String(w.canceled)} />
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Sessions count as completed only when you mark them. These numbers show what you did,
        not how your technique changed.
      </p>
    </Card>
  );
}

function Preferences({ view }: { view: TrainingOverview }) {
  const s = view.swimmer;
  const rows: [string, string][] = [
    ["Level", s.level ? levelLabel(s.level as SwimLevel) : "Not set"],
    [
      "Goals",
      s.goals.length
        ? s.goals
            .map((g) => goalLabel(g) + (g === s.primary_goal ? " (main)" : ""))
            .join(", ")
        : "None chosen",
    ],
    ["Sessions per week", s.sessions_per_week === null ? "Not set" : String(s.sessions_per_week)],
    ["Time per session", s.session_minutes === null ? "Not set" : formatMinutes(s.session_minutes)],
    [
      "Days you can swim",
      s.days.length
        ? DAY_OPTIONS.filter((d) => s.days.includes(d.value))
            .map((d) => d.label)
            .join(", ")
        : "No preference set",
    ],
    ["Preferred time", s.time_of_day || "No preference"],
    ["Difficulty", s.difficulty || "Not set"],
    ["Typical distance", s.typical_distance_m ? `${s.typical_distance_m} m` : "Not set"],
    ["Strokes", s.strokes.length ? s.strokes.join(", ") : "Not set"],
    [
      "Equipment",
      s.equipment.length ? s.equipment.map((e) => e.replace("_", " ")).join(", ") : "None listed",
    ],
  ];
  return (
    <>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 border-b border-slate-100 py-1.5">
            <dt className="text-slate-500">{label}</dt>
            <dd className="text-right font-medium text-slate-900">{value}</dd>
          </div>
        ))}
      </dl>
      {s.missing.length > 0 && (
        <p className="mt-3 rounded-xl bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
          Not set yet: {s.missing.join(", ")}. Plans use cautious defaults for these and say so.
        </p>
      )}
      <p className="mt-3 text-sm text-slate-600">
        Level and goals are edited in{" "}
        <Link href="/profile" className="font-medium text-sky-700 hover:text-sky-900">
          your profile
        </Link>
        .
      </p>
    </>
  );
}

const ANALYSIS_NOTE: Record<TrainingOverview["analysis"]["state"], string> = {
  none: "No analysed video yet, so nothing here comes from your own swimming. Recommendations follow your goals.",
  unavailable:
    "Your latest video could not be measured, so nothing here comes from it. Recommendations follow your goals.",
  no_supported_issue:
    "Your latest analysis found no supported technique issue. That is a normal result. Recommendations follow your goals and are not corrections.",
  supported:
    "Your latest analysis has a supported finding. The practice linked to it is marked Analysis-based. It is something to look at, not a confirmed fault.",
};

function Basis({ view }: { view: TrainingOverview }) {
  return (
    <Card title="Recommended practice">
      <p className="text-sm text-slate-700">{ANALYSIS_NOTE[view.analysis.state]}</p>
      {view.analysis.video_id && (
        <p className="mt-1 text-sm">
          <Link
            href={`/history/${view.analysis.video_id}`}
            className="font-medium text-sky-700 hover:text-sky-900"
          >
            Open your latest analysis
          </Link>
        </p>
      )}
      {view.recommendations.length === 0 ? (
        <p className="mt-3 text-sm text-slate-600">
          No practice matches your level and equipment yet.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {view.recommendations.map((r) => (
            <li key={r.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-semibold text-slate-900">{r.activity_name}</p>
                <Badge tone={basisTone(r.basis)}>{basisLabel(r.basis)}</Badge>
                <Badge tone="slate">{evidenceLabel(r.evidence_class)}</Badge>
              </div>
              <p className="mt-1.5 text-sm text-slate-700">{r.reason}</p>
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-medium text-sky-700">
                  What it rests on and its limits
                </summary>
                <dl className="mt-2 space-y-1.5 text-sm text-slate-700">
                  <div>
                    <dt className="inline font-medium">Used: </dt>
                    <dd className="inline">{r.inputs_used.join(", ")}</dd>
                  </div>
                  {r.finding_titles.length > 0 && (
                    <div>
                      <dt className="inline font-medium">Finding: </dt>
                      <dd className="inline">{r.finding_titles.join("; ")}</dd>
                    </div>
                  )}
                  {r.watch_for && (
                    <div>
                      <dt className="inline font-medium">What you can notice: </dt>
                      <dd className="inline">{r.watch_for}</dd>
                    </div>
                  )}
                  {r.video_can_measure && (
                    <div>
                      <dt className="inline font-medium">What a later video can measure: </dt>
                      <dd className="inline">{r.video_can_measure}</dd>
                    </div>
                  )}
                  {[...r.assumptions, ...r.limitations].map((line) => (
                    <div key={line} className="text-slate-600">
                      {line}
                    </div>
                  ))}
                </dl>
              </details>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PlanBody({ plan }: { plan: TrainingPlan }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={basisTone(plan.basis)}>{basisLabel(plan.basis)}</Badge>
        {plan.inputs.analysis_removed && (
          <Badge tone="slate">Based on a video you have since deleted</Badge>
        )}
      </div>
      <p className="mt-2 text-sm text-slate-700">{plan.summary}</p>
      {plan.explained && (
        <p className="mt-2 rounded-xl bg-sky-50 px-3 py-2 text-sm text-slate-700">
          {plan.explained}{" "}
          <span className="text-xs text-slate-500">(Reworded by a language model.)</span>
        </p>
      )}
      <p className="mt-1 text-xs text-slate-500">{basisNote(plan.basis)}</p>
      {[...plan.notes, ...plan.assumptions].length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
          {[...plan.notes, ...plan.assumptions].map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function Generator({ view, onSaved }: { view: TrainingOverview; onSaved: () => void }) {
  const [start, setStart] = useState(localIso(new Date()));
  const [preview, setPreview] = useState<TrainingPlan | null>(null);
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  async function generate(kind: "session" | "week") {
    setBusy(true);
    setError(null);
    setConflict(null);
    setSaved(null);
    const res = await previewPlan(kind, start);
    setBusy(false);
    if (res.ok) setPreview(res.data);
    else setError(res.error);
  }

  async function save(opts: { confirm?: boolean; discard_edits?: boolean } = {}) {
    if (!preview) return;
    setBusy(true);
    setError(null);
    const res = await savePlan(preview.kind, preview.start_date, opts);
    setBusy(false);
    if (!res.ok) return setError(res.error);
    if (!res.data.saved) return setConflict(res.data.conflict);
    setPreview(null);
    setConflict(null);
    setSaved(
      `Saved ${res.data.plan.sessions.length} ${res.data.plan.sessions.length === 1 ? "session" : "sessions"} to your calendar.`,
    );
    onSaved();
  }

  return (
    <Card title="Make a plan">
      <p className="text-sm text-slate-600">
        The plan is written by fixed rules from your settings{view.llm_enabled ? "" : ", with no AI involved"}. Review it
        first; nothing is saved until you say so.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="block text-sm font-medium text-slate-700">
          Start date
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="mt-1 block rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm"
          />
        </label>
        <Button onClick={() => generate("week")} disabled={busy || !start}>
          Plan 7 days
        </Button>
        <Button variant="secondary" onClick={() => generate("session")} disabled={busy || !start}>
          Plan one session
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="mt-3 text-sm text-teal-800">
          {saved}{" "}
          <Link href="/calendar" className="font-medium text-sky-700 hover:text-sky-900">
            Open calendar
          </Link>
        </p>
      )}

      {preview && (
        <div className="mt-5 rounded-2xl border border-sky-200 bg-sky-50/40 p-4" aria-live="polite">
          <p className="text-xs font-semibold tracking-wide text-sky-800 uppercase">
            Preview, not saved yet
          </p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900">{preview.title}</h3>
          <div className="mt-2">
            <PlanBody plan={preview} />
          </div>
          <ol className="mt-4 space-y-3">
            {preview.sessions.map((s) => (
              <li key={s.date + s.title} className="rounded-2xl border border-slate-200 bg-surface p-4">
                <p className="text-xs font-medium text-slate-500">
                  {formatDay(s.date)}
                  {s.time ? ` · ${s.time}` : ""}
                </p>
                <p className="font-semibold text-slate-900">{s.title}</p>
                <p className="text-sm text-slate-600">{sessionMeta(s)}</p>
                <p className="mt-1 text-sm text-slate-700">{s.objective}</p>
                <ul className="mt-3 space-y-2">
                  {s.items.map((item) => (
                    <ActivityRow key={item.activity_id} item={item} />
                  ))}
                </ul>
                {s.checkpoint && (
                  <p className="mt-3 text-sm text-slate-600">
                    <span className="font-medium text-slate-900">{s.checkpoint.title}.</span>{" "}
                    {s.checkpoint.what_to_film}
                  </p>
                )}
              </li>
            ))}
          </ol>
          {preview.rest_days.length > 0 && (
            <p className="mt-3 text-sm text-slate-600">
              No swimming planned on{" "}
              {preview.rest_days
                .map((d) => formatDay(d.date, { weekday: "short", day: "numeric" }))
                .join(", ")}
              . {preview.rest_days[0].guidance}
            </p>
          )}
          <details className="mt-3">
            <summary className="cursor-pointer text-xs font-medium text-slate-600">
              Limits of this plan
            </summary>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {preview.limitations.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </details>

          {conflict ? (
            <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3" role="group" aria-label="These dates already have a plan">
              {conflict.kind === "week_overlap" ? (
                <>
                  <p className="text-sm font-medium text-amber-900">
                    These dates already have a plan.
                  </p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-amber-900">
                    {conflict.plans.map((p) => (
                      <li key={p.id}>
                        {p.title} (version {p.version}): {p.recorded} recorded, {p.edited} edited
                        by you, {p.unedited} untouched.
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1 text-sm text-amber-900">
                    Completed, skipped and cancelled sessions are always kept. The old version
                    stays in your records.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button onClick={() => save({ confirm: true })} disabled={busy}>
                      Replace, keep my edited sessions
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => save({ confirm: true, discard_edits: true })}
                      disabled={busy}
                    >
                      Replace my edited sessions too
                    </Button>
                    <Button variant="secondary" onClick={() => setConflict(null)} disabled={busy}>
                      Keep the current plan
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm font-medium text-amber-900">
                    You already have a session planned that day
                    {conflict.sessions[0] ? `: ${conflict.sessions[0].title}` : ""}.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button onClick={() => save({ confirm: true })} disabled={busy}>
                      Add this one as well
                    </Button>
                    <Button variant="secondary" onClick={() => setConflict(null)} disabled={busy}>
                      Don&apos;t add it
                    </Button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button onClick={() => save()} disabled={busy || preview.sessions.length === 0}>
                {busy ? "Saving…" : "Save to my calendar"}
              </Button>
              <Button variant="secondary" onClick={() => setPreview(null)} disabled={busy}>
                Discard
              </Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function SavedPlan({
  plan,
  view,
  onChanged,
}: {
  plan: TrainingPlan;
  view: TrainingOverview;
  onChanged: () => void;
}) {
  return (
    <Card
      title={`${plan.title}${plan.version > 1 ? ` (version ${plan.version})` : ""}`}
      action={<ButtonLink href={`/calendar?date=${plan.start_date}`} variant="secondary">In calendar</ButtonLink>}
    >
      <PlanBody plan={plan} />
      {plan.sessions.length === 0 ? (
        <p className="mt-3 text-sm text-slate-600">This plan has no sessions left.</p>
      ) : (
        <div className="mt-4 space-y-3">
          {plan.sessions.map((s) => (
            <SessionCard key={s.id} session={s} library={view.library} onChanged={onChanged} />
          ))}
        </div>
      )}
    </Card>
  );
}

function History({ view }: { view: TrainingOverview }) {
  return (
    <Card title="Training history">
      {view.history.length === 0 ? (
        <p className="text-sm text-slate-600">
          Nothing recorded yet. Sessions appear here once you mark them completed, skipped or
          cancelled.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {view.history.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">{s.title}</p>
                <p className="text-xs text-slate-500">
                  Planned for {formatDay(s.date)}
                  {s.completion ? ` · done ${formatDay(s.completion.completed_on)}` : ""}
                  {s.status === "completed"
                    ? ` · ${s.items.filter((i) => i.done).length} of ${s.items.length} activities`
                    : ""}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Badge tone={statusTone(s.status)}>{statusLabel(s.status)}</Badge>
                <Link
                  href={`/calendar?date=${s.date}`}
                  className="text-sm font-medium text-sky-700 hover:text-sky-900"
                >
                  Open
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-slate-500">
        {view.totals.completed} completed and {view.totals.skipped} skipped in total. This is a
        record of practice, kept apart from what your videos measure.
      </p>
    </Card>
  );
}

function Library({ view }: { view: TrainingOverview }) {
  const sources = new Map(view.sources.map((s) => [s.id, s]));
  return (
    <Card title="Activity library and sources">
      <p className="text-sm text-slate-600">
        Every plan is built only from these activities. Durations, repeats and rest are
        AquaTrack&apos;s own conservative choices. No source shows that an activity changes a
        particular swimmer&apos;s technique or times.
      </p>
      <ul className="mt-4 space-y-2">
        {view.library.map((a) => (
          <li key={a.id} className="rounded-xl bg-slate-50 px-3 py-2.5">
            <details>
              <summary className="cursor-pointer text-sm font-medium text-slate-900">
                {a.name}{" "}
                <span className="font-normal text-slate-500">
                  · {evidenceLabel(a.evidence_class)}
                  {a.not_offered ? " · not available for you" : ""}
                </span>
              </summary>
              <p className="mt-2 text-sm text-slate-700">{a.purpose}</p>
              {a.not_offered && <p className="mt-1 text-sm text-amber-800">{a.not_offered}</p>}
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {a.instructions.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
                {[...a.safety, ...a.limitations].map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              {a.source_ids.length > 0 && (
                <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
                  {a.source_ids.map((sid) => {
                    const s = sources.get(sid);
                    return s ? (
                      <li key={sid}>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-sky-700 hover:text-sky-900"
                        >
                          {s.title}
                        </a>{" "}
                        ({s.publisher}
                        {s.year ? `, ${s.year}` : ""};{" "}
                        {s.read === "abstract" ? "abstract read" : "coaching page read"}). {s.says}{" "}
                        <span className="text-slate-500">{s.limits}</span>
                      </li>
                    ) : null;
                  })}
                </ul>
              )}
            </details>
          </li>
        ))}
      </ul>
    </Card>
  );
}
