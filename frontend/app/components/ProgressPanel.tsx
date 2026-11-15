"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useUser } from "@/app/components/AppShell";
import {
  Badge,
  ButtonLink,
  Card,
  LoadingState,
  Stat,
} from "@/app/components/ui";
import { formatMetric, unitLabel } from "@/app/lib/analysisV1";
import {
  chartPoints,
  followUpLabel,
  recordViews,
  shortDate,
  stateLabel,
  stateTone,
  type ProgressMetric,
  type ProgressView,
} from "@/app/lib/history";
import { fetchProgress } from "@/app/lib/historyApi";
import {
  formatSwimTime,
  goalLabel,
  loadProfile,
  type Profile,
} from "@/app/lib/profile";

// The swimmer's own progress, from their stored analyses. Only sessions that may be compared
// share a line; everything else is listed with the reason. No example data in here.
export function ProgressPanel() {
  const user = useUser();
  const uid = user?.uid;
  const [view, setView] = useState<ProgressView | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    if (!uid) return;
    let live = true;
    fetchProgress().then((res) => {
      if (!live) return;
      if (res.ok) setView(res.data);
      else setError(res.error);
    });
    loadProfile(uid)
      .then((p) => live && setProfile(p))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [uid]);

  if (error)
    return (
      <Card title="Your progress">
        <p role="alert" className="text-sm text-red-700">
          Couldn&apos;t load your progress. {error}
        </p>
      </Card>
    );
  if (view === undefined)
    return (
      <Card title="Your progress">
        <LoadingState label="Loading your progress…" />
      </Card>
    );
  if (view === null)
    return (
      <Card title="Your progress">
        <p className="text-sm text-slate-600">
          Your progress is in a format this page can&apos;t show.
        </p>
      </Card>
    );

  const records = profile ? recordViews(profile.pbs, profile.target) : [];
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat label="Videos uploaded" value={`${view.videos}`} />
        <Stat label="Analyzed" value={`${view.analyzed}`} />
        <Stat
          label="Comparable groups"
          value={`${view.series.filter((s) => s.sessions.length >= 2).length}`}
          note="with two or more videos"
        />
        <Stat
          label="Open checkpoints"
          value={`${view.openCheckpoints.length}`}
        />
      </div>

      <Card title={view.baseline ? "Your baseline" : "Measured changes"}>
        <p className="text-sm text-slate-600">{view.note}</p>
        {view.analyzed === 0 && (
          <div className="mt-4">
            <ButtonLink href="/analyze">Upload your first swim</ButtonLink>
          </div>
        )}
        {profile && profile.goals.length > 0 && (
          <p className="mt-3 text-xs text-slate-500">
            Your goals: {profile.goals.map(goalLabel).join(", ")}. Goals decide
            what is shown first; they are not evidence that anything needs
            fixing.
          </p>
        )}
      </Card>

      {view.series.map((s) => (
        <Card
          key={s.key}
          title={`${s.distance ? `${s.distance} ` : ""}${s.stroke || "Swim"} · ${s.camera || "view not given"}`}
        >
          <p className="mb-4 text-sm text-slate-600">
            {s.sessions.length === 1
              ? "One video so far. A second one of the same distance and effort, filmed the same way, starts a trend."
              : `${s.sessions.length} videos that may be compared with each other, oldest first.`}
          </p>
          {s.metrics.length === 0 && (
            <p className="text-sm text-slate-600">
              None of this group&apos;s measurements passed their checks, so
              nothing is drawn.
            </p>
          )}
          <ul className="divide-y divide-slate-100">
            {orderForGoals(s.metrics, profile).map((m) => (
              <Trend key={m.metricKey} metric={m} />
            ))}
          </ul>
          {s.sessions.length >= 2 && (
            <p className="mt-4 text-sm">
              <Link
                href={`/compare?a=${s.sessions[s.sessions.length - 2].videoId}&b=${s.sessions[s.sessions.length - 1].videoId}`}
                className="font-medium text-sky-700 hover:text-sky-900"
              >
                Compare the two most recent videos
              </Link>
            </p>
          )}
        </Card>
      ))}

      {(view.followups.length > 0 || view.openCheckpoints.length > 0) && (
        <Card title="Checkpoints">
          {view.followups.length > 0 && (
            <>
              <p className="mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase">
                From your previous video, answered by your latest
              </p>
              <ul className="mb-4 space-y-3">
                {view.followups.map((f) => (
                  <li key={f.checkpointId} className="text-sm">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-medium text-slate-900">
                        {f.title}
                      </span>
                      <Badge tone="slate">{followUpLabel[f.state]}</Badge>
                    </div>
                    <p className="mt-0.5 text-slate-600">{f.explanation}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
          {view.openCheckpoints.length > 0 && (
            <>
              <p className="mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase">
                For your next video · {followUpLabel.not_yet_evaluated}
              </p>
              <ul className="space-y-3">
                {view.openCheckpoints.map((c) => (
                  <li key={c.id} className="text-sm">
                    <span className="font-medium text-slate-900">
                      {c.title}
                    </span>
                    <p className="mt-0.5 text-slate-600">{c.whatToFilm}</p>
                    {c.reason && (
                      <p className="text-xs text-slate-500">Why: {c.reason}</p>
                    )}
                  </li>
                ))}
              </ul>
              {view.latestVideoId && (
                <p className="mt-3 text-sm">
                  <Link
                    href={`/history/${view.latestVideoId}`}
                    className="font-medium text-sky-700 hover:text-sky-900"
                  >
                    Open the video they came from
                  </Link>
                </p>
              )}
            </>
          )}
        </Card>
      )}

      {view.history.length > 0 && (
        <Card title="What each analysis found">
          <ul className="divide-y divide-slate-100">
            {[...view.history].reverse().map((h) => (
              <li key={h.videoId} className="py-3 text-sm first:pt-0 last:pb-0">
                <Link
                  href={`/history/${h.videoId}`}
                  className="font-medium text-sky-700 hover:text-sky-900"
                >
                  {shortDate(h.recordedAt) || "Video"} · {h.fileName || "video"}
                </Link>
                <p className="mt-0.5 text-slate-600">
                  {h.observations}{" "}
                  {h.observations === 1 ? "observation" : "observations"}
                  {h.issueCandidates.length > 0
                    ? `. Worth a look: ${h.issueCandidates.join("; ")}`
                    : ". Nothing flagged"}
                  {h.priorities.length > 0
                    ? `. Ranked as a priority: ${h.priorities.join("; ")}`
                    : ""}
                  .
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {(view.notIncluded.length > 0 || view.repeatedLimitations.length > 0) && (
        <Card title="What could not be included">
          <ul className="space-y-2.5 text-sm">
            {view.repeatedLimitations.map((text) => (
              <li key={text} className="text-slate-600">
                {text}
              </li>
            ))}
            {view.notIncluded.map(({ session, reasons }) => (
              <li key={session.videoId}>
                <Link
                  href={`/history/${session.videoId}`}
                  className="font-medium text-sky-700 hover:text-sky-900"
                >
                  {shortDate(session.recordedAt) || "Video"}
                </Link>
                <span className="text-slate-600"> · {reasons.join(" ")}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Your times">
        <p className="mb-3 text-sm text-slate-600">
          <Badge tone="slate">Entered by you</Badge> These are the times on your
          profile. They are not measured from video and are not linked to any
          technique measurement.
        </p>
        {records.length > 0 ? (
          <ul className="grid gap-3 sm:grid-cols-3">
            {records.map((r) => (
              <li
                key={`${r.event}|${r.pool}`}
                className="rounded-xl bg-slate-50 p-4"
              >
                <p className="text-sm text-slate-600">
                  {r.event} · {r.pool}
                </p>
                <p className="mt-1 font-display text-2xl font-semibold text-slate-900 tabular-nums">
                  {formatSwimTime(r.best)}
                </p>
                {r.target !== null && r.gap !== null && (
                  <p className="mt-1 text-xs text-slate-500">
                    Your target: {formatSwimTime(r.target)}
                    {r.gap > 0
                      ? ` (${r.gap.toFixed(2)} s to go)`
                      : " (reached)"}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">
            No times on your profile yet. Add personal bests on your profile to
            see them here.
          </p>
        )}
        {profile?.target && !records.some((r) => r.target !== null) && (
          <p className="mt-3 text-sm text-slate-600">
            Your target: {formatSwimTime(profile.target.seconds)} in the{" "}
            {profile.target.event} ({profile.target.pool}). Add a personal best
            for the same event and pool to see the gap.
          </p>
        )}
        {profile?.weak_note && (
          <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
            <span className="font-medium text-slate-900">Your own note. </span>
            {profile.weak_note}
            <span className="block text-xs text-slate-500">
              In your words, from your profile. It is not a measurement and is
              not analysed.
            </span>
          </p>
        )}
      </Card>
    </div>
  );
}

// Metrics that belong to a goal the swimmer chose come first. Nothing is added or hidden.
const goalMetrics: Record<string, string[]> = {
  stroke_consistency: ["rhythm_variation", "cycle_duration"],
  body_alignment: ["body_line_angle", "leg_line_angle", "head_height"],
  speed: ["stroke_rate", "cycle_duration"],
  endurance: ["cycle_duration"],
};
function orderForGoals(
  metrics: ProgressMetric[],
  profile: Profile | null,
): ProgressMetric[] {
  const first = new Set(
    (profile?.goals ?? []).flatMap((g) => goalMetrics[g] ?? []),
  );
  return [...metrics].sort(
    (a, b) => Number(first.has(b.metricKey)) - Number(first.has(a.metricKey)),
  );
}

function Trend({ metric: m }: { metric: ProgressMetric }) {
  const unit = unitLabel[m.unit] ?? m.unit;
  const width = 280;
  const height = 64;
  const pts = chartPoints(
    m.points.map((p) => p.value),
    width,
    height,
  );
  return (
    <li className="py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-slate-900">{m.label}</h3>
        {m.overall ? (
          <Badge tone={stateTone[m.overall.state]}>
            {stateLabel[m.overall.state]}
          </Badge>
        ) : (
          <Badge tone="slate">Baseline</Badge>
        )}
      </div>
      {m.overall &&
        m.overall.change !== null &&
        m.overall.threshold !== null && (
          <p className="mt-1 text-xs text-slate-500">
            First to latest: {formatMetric(m.overall.change, m.unit)} {unit}.
            Differences under {formatMetric(m.overall.threshold, m.unit)} {unit}{" "}
            can&apos;t be told from measurement noise. A change is not a
            judgement.
          </p>
        )}
      {m.points.length >= 2 && (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="mt-2 h-16 w-full max-w-xs text-sky-700"
          role="img"
          aria-label={`${m.label} across ${m.points.length} videos: ${m.points.map((p) => `${formatMetric(p.value, m.unit)} ${unit}`).join(", ")}`}
        >
          <polyline
            points={pts.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          />
          {pts.map((p, i) => (
            <circle
              key={m.points[i].videoId}
              cx={p.x}
              cy={p.y}
              r="4"
              fill="currentColor"
            />
          ))}
        </svg>
      )}
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {m.points.map((p) => (
          <li key={p.videoId}>
            <Link
              href={`/history/${p.videoId}`}
              className="inline-block rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 tabular-nums transition hover:bg-sky-100 hover:text-sky-900"
            >
              {shortDate(p.recordedAt) || "Video"} ·{" "}
              {formatMetric(p.value, m.unit)}
              {unit === "°" ? unit : ` ${unit}`}
            </Link>
          </li>
        ))}
      </ul>
    </li>
  );
}
