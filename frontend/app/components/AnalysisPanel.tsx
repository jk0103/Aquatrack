"use client";

import { useState } from "react";

import { Badge, Button, Card, LoadingState } from "@/app/components/ui";
import {
  formatMetric,
  formatNumber,
  gradeLabel,
  gradeTone,
  groupTitle,
  statusLabel,
  statusTone,
  unitLabel,
  type AnalysisV1,
  type Coverage,
  type MetricGroup,
  type MetricV1,
  type QualityReport,
} from "@/app/lib/analysisV1";
import {
  cancelAnalysis,
  progressLabel,
  requestAnalysis,
  type VideoRecord,
} from "@/app/lib/videos";

// Everything on this panel comes from the swimmer's own video: the job state on the video
// record and, once it's ready, the stored analysis. Nothing here is example data.
export function AnalysisPanel({
  video,
  analysis,
  analysisError,
  onSeek,
}: {
  video: VideoRecord;
  // undefined while the result is loading; null when it couldn't be read.
  analysis: AnalysisV1 | null | undefined;
  analysisError: string | null;
  onSeek?: (seconds: number) => void;
}) {
  if (video.status === "ready") {
    if (analysisError)
      return (
        <Card title="Analysis">
          <p role="alert" className="text-sm text-red-700">
            Couldn&apos;t load the analysis. {analysisError}
          </p>
        </Card>
      );
    if (analysis === undefined)
      return (
        <Card title="Analysis">
          <LoadingState label="Loading the analysis…" />
        </Card>
      );
    if (analysis === null)
      return (
        <Card title="Analysis">
          <p className="text-sm text-slate-600">
            The analysis finished, but its results are in a format this page
            can&apos;t show.
          </p>
        </Card>
      );
    // Results from before metrics existed (schema 1.0) keep their original layout.
    return analysis.metrics.length > 0 && analysis.coverage ? (
      <MetricResults
        analysis={analysis}
        coverage={analysis.coverage}
        onSeek={onSeek}
      />
    ) : (
      <Results analysis={analysis} onSeek={onSeek} />
    );
  }
  return <JobStatus video={video} />;
}

function JobStatus({ video }: { video: VideoRecord }) {
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  async function start() {
    setSending(true);
    setSendError(null);
    const res = await requestAnalysis(video.id);
    // On success the video record changes to "queued" and this panel re-renders by itself.
    if (!res.ok) setSendError(res.error);
    setSending(false);
  }

  async function cancel() {
    setSending(true);
    setSendError(null);
    const res = await cancelAnalysis(video.id);
    if (!res.ok) setSendError(res.error);
    setSending(false);
  }

  const working = video.status === "queued" || video.status === "analyzing";
  const failed = video.status === "failed";
  const canRetry = failed && video.job?.retryable === true;

  return (
    <Card title="Analysis">
      {working && (
        <div role="status" aria-live="polite">
          <LoadingState
            label={
              video.status === "queued"
                ? "Waiting to start…"
                : "Analyzing your swim. This page updates when it's done."
            }
          />
          {video.status === "analyzing" && progressLabel(video.job) && (
            <p className="text-sm text-slate-700">{progressLabel(video.job)}.</p>
          )}
          <p className="text-sm text-slate-600">
            You can leave this page; the analysis carries on and is picked up again if
            the server restarts.
          </p>
          <div className="mt-3">
            <Button variant="secondary" onClick={cancel} disabled={sending}>
              {sending ? "Cancelling…" : "Cancel analysis"}
            </Button>
          </div>
        </div>
      )}
      {(video.status === "uploaded" || video.status === "canceled") && (
        <>
          <p className="text-sm text-slate-600">
            {video.status === "canceled"
              ? "You cancelled the analysis. Nothing from it was kept; your upload is still saved."
              : "This video hasn't been analyzed yet."}
          </p>
          <div className="mt-4">
            <Button onClick={start} disabled={sending}>
              {sending ? "Starting…" : "Analyze this video"}
            </Button>
          </div>
        </>
      )}
      {failed && (
        <div role="alert">
          <p className="font-medium text-slate-900">
            The analysis couldn&apos;t finish.
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {video.job?.errorMessage ??
              "Something went wrong while analysing this video."}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Your upload is still saved.
          </p>
          {canRetry ? (
            <div className="mt-4">
              <Button onClick={start} disabled={sending}>
                {sending ? "Starting…" : "Try again"}
              </Button>
            </div>
          ) : (
            <p className="mt-3 text-xs text-slate-500">
              {video.job && video.job.attempts > 1
                ? "This video has been tried the maximum number of times."
                : "Trying again won't help for this file."}
            </p>
          )}
        </div>
      )}
      {sendError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {sendError}
        </p>
      )}
    </Card>
  );
}

function Results({
  analysis,
  onSeek,
}: {
  analysis: AnalysisV1;
  onSeek?: (seconds: number) => void;
}) {
  const { stroke, quality } = analysis;
  const trusted = stroke.cycles.filter((c) => c.trusted);
  const skipped = stroke.cycles.length - trusted.length;
  return (
    <div className="space-y-6">
      <Card title="Stroke timing">
        {analysis.measurements.length > 0 ? (
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {analysis.measurements.map((m) => (
              <div key={m.key}>
                <dt className="text-xs text-slate-500">{m.label}</dt>
                <dd className="mt-0.5 font-display text-2xl font-semibold text-slate-900 tabular-nums">
                  {formatNumber(m)}
                  {m.unit && (
                    <span className="ml-1 font-sans text-sm font-medium text-slate-500">
                      {m.unit}
                    </span>
                  )}
                </dd>
                {m.basis && (
                  <dd className="mt-0.5 text-xs text-slate-500">
                    From {m.basis}
                  </dd>
                )}
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-slate-600">
            <span className="font-medium text-slate-900">
              Not measurable in this clip.
            </span>{" "}
            {stroke.reason}
          </p>
        )}
        {stroke.measurable && (
          <p className="mt-4 text-xs text-slate-500">
            One cycle is one full turn of one arm. Measured from{" "}
            {stroke.cycleCount.left + stroke.cycleCount.right} reliable cycles
            {skipped > 0
              ? `; ${skipped} unclear ${skipped === 1 ? "cycle was" : "cycles were"} left out`
              : ""}
            .
          </p>
        )}
        {trusted.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase">
              Stroke cycles
            </p>
            <ul className="flex flex-wrap gap-1.5">
              {trusted.map((c, i) => (
                <li key={`${c.arm}-${c.start}`}>
                  <button
                    type="button"
                    onClick={() => onSeek?.(c.start)}
                    disabled={!onSeek}
                    title={`${c.arm} arm, ${c.duration.toFixed(2)} s`}
                    className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 tabular-nums transition hover:bg-sky-100 hover:text-sky-900 focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:outline-none disabled:hover:bg-slate-100"
                  >
                    {i + 1} · {c.arm === "left" ? "L" : "R"} ·{" "}
                    {c.start.toFixed(1)} s
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <QualityCard quality={quality} />

      <Card title="Not measured yet">
        <ul className="space-y-2.5">
          {analysis.unavailable.map((u) => (
            <li key={u.key} className="text-sm">
              <span className="font-medium text-slate-900">{u.label}</span>
              <span className="text-slate-600"> · {u.reason}</span>
            </li>
          ))}
        </ul>
      </Card>

      <p className="text-xs text-slate-500">
        Analysis v{analysis.schemaVersion}
        {analysis.models.detector
          ? ` · detector ${analysis.models.detector}`
          : ""}
        {analysis.models.pose ? ` · pose ${analysis.models.pose}` : ""}
        {analysis.createdAt
          ? ` · ${analysis.createdAt.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
          : ""}
      </p>
    </div>
  );
}

const groupOrder: MetricGroup[] = ["timing", "body", "arm", "consistency"];

// Schema 1.1: every number carries its own reliability. Nothing here judges the technique.
function MetricResults({
  analysis,
  coverage,
  onSeek,
}: {
  analysis: AnalysisV1;
  coverage: Coverage;
  onSeek?: (seconds: number) => void;
}) {
  const shown = new Set(analysis.metrics.map((m) => m.key));
  const notMeasured = analysis.unavailable.filter((u) => !shown.has(u.key));
  return (
    <div className="space-y-6">
      <CoverageCard coverage={coverage} />

      {groupOrder.map((group) => {
        const metrics = analysis.metrics.filter((m) => m.group === group);
        if (metrics.length === 0) return null;
        const armNote =
          group === "arm" && coverage.cameraSide.arm
            ? `Read only from the ${coverage.cameraSide.arm} arm, the one nearer the camera, and only while it is under water.`
            : null;
        return (
          <Card key={group} title={groupTitle[group]}>
            {armNote && (
              <p className="mb-3 text-xs text-slate-500">{armNote}</p>
            )}
            <ul className="divide-y divide-slate-100">
              {metrics.map((m) => (
                <MetricRow key={m.key} metric={m} onSeek={onSeek} />
              ))}
            </ul>
          </Card>
        );
      })}

      <QualityCard quality={analysis.quality} />

      {notMeasured.length > 0 && (
        <Card title="Not measured from this kind of video">
          <ul className="space-y-2.5">
            {notMeasured.map((u) => (
              <li key={u.key} className="text-sm">
                <span className="font-medium text-slate-900">{u.label}</span>
                <span className="text-slate-600"> · {u.reason}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <p className="text-xs text-slate-500">
        These are measurements from the video, not a judgement of the stroke.
        Analysis v{analysis.schemaVersion}
        {analysis.models.detector
          ? ` · detector ${analysis.models.detector}`
          : ""}
        {analysis.models.pose ? ` · pose ${analysis.models.pose}` : ""}
        {analysis.createdAt
          ? ` · ${analysis.createdAt.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
          : ""}
      </p>
    </div>
  );
}

function MetricRow({
  metric: m,
  onSeek,
}: {
  metric: MetricV1;
  onSeek?: (seconds: number) => void;
}) {
  const unit = unitLabel[m.unit] ?? m.unit;
  const measured = m.status !== "unavailable" && m.value !== null;
  return (
    <li className="py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-slate-900">{m.label}</h3>
        <Badge tone={statusTone[m.status]}>{statusLabel[m.status]}</Badge>
      </div>

      {measured && m.value !== null ? (
        <>
          <p className="mt-1 font-display text-2xl font-semibold text-slate-900 tabular-nums">
            {formatMetric(m.value, m.unit)}
            <span className="ml-1 font-sans text-sm font-medium text-slate-500">
              {unit}
            </span>
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {m.low !== null && m.high !== null && m.cycles > 1
              ? `Middle half of the cycles: ${formatMetric(m.low, m.unit)} to ${formatMetric(m.high, m.unit)}. `
              : ""}
            {m.basis ? `From ${m.basis}.` : ""}
            {m.coveragePct !== null
              ? ` Joints usable in ${Math.round(m.coveragePct)}% of those frames.`
              : ""}
          </p>
        </>
      ) : (
        <p className="mt-1 text-sm text-slate-600">{m.reason}</p>
      )}

      {measured && m.status === "limited" && m.reason && (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span className="font-medium">Read with care.</span> {m.reason}
        </p>
      )}

      {measured && m.samples.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {m.samples.map((s) => (
            <li key={`${s.t}-${s.label}`}>
              <button
                type="button"
                onClick={() => onSeek?.(s.t)}
                disabled={!onSeek}
                aria-label={`${m.label}: ${formatMetric(s.value, m.unit)} ${unit} at ${s.t.toFixed(1)} seconds. Show in the video.`}
                className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 tabular-nums transition hover:bg-sky-100 hover:text-sky-900 focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:outline-none disabled:hover:bg-slate-100"
              >
                {s.label ? `${s.label} · ` : ""}
                {formatMetric(s.value, m.unit)} · {s.t.toFixed(1)} s
              </button>
            </li>
          ))}
        </ul>
      )}

      <details className="mt-2 text-sm text-slate-600">
        <summary className="cursor-pointer text-xs font-medium text-sky-700 hover:text-sky-900">
          What this is and its limits
        </summary>
        <p className="mt-2">{m.description}</p>
        <ul className="mt-1.5 list-disc space-y-1 pl-5 text-xs text-slate-500">
          {m.limitations.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </details>
    </li>
  );
}

const viewLabel = {
  steady: "Steady",
  changing: "Changed during the clip",
  unknown: "Can't tell",
};
const viewTone = {
  steady: "teal",
  changing: "amber",
  unknown: "slate",
} as const;

const cycleStatusLabel = {
  complete: "All followed",
  partial: "Partly followed",
  none: "None followed",
};
const cycleStatusTone = {
  complete: "teal",
  partial: "amber",
  none: "slate",
} as const;

// Separate levels, so good tracking is never read as "every number is right".
function CoverageCard({ coverage: c }: { coverage: Coverage }) {
  const near = c.arms.find((a) => a.cameraSide);
  const pct = (v: number) => `${Math.round(v)}%`;
  const measured = c.metricsReliable + c.metricsLimited;
  return (
    <Card title="What this analysis can stand behind">
      <p className="mb-4 text-sm text-slate-600">{c.summary}</p>
      <dl className="space-y-4">
        <div>
          <dt className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
            Following the swimmer
            <Badge tone={gradeTone[c.trackingGrade]}>
              {gradeLabel[c.trackingGrade]}
            </Badge>
          </dt>
          <dd className="mt-1 text-sm text-slate-600">
            Whether one swimmer was followed and the joints were placed. It does
            not vouch for the numbers below.
          </dd>
        </div>
        {c.view && (
          <div>
            <dt className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
              Camera view
              <Badge tone={viewTone[c.view.status]}>
                {viewLabel[c.view.status]}
              </Badge>
            </dt>
            <dd className="mt-1 text-sm text-slate-600">
              {c.view.status === "changing"
                ? c.view.note
                : c.view.status === "steady"
                  ? "The swimmer stayed about the same size in the picture. That rules out a camera the swimmer swims past at an angle; it does not prove the view is exactly side-on."
                  : "Too few stroke cycles to tell whether the camera's view changed."}{" "}
              The camera&apos;s angle itself can&apos;t be measured from one
              video.
            </dd>
          </div>
        )}
        <div>
          <dt className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
            Arm points
            <Badge tone={c.cameraSide.arm ? "teal" : "slate"}>
              {c.cameraSide.arm
                ? `${c.cameraSide.arm} arm nearer the camera`
                : "Camera side unclear"}
            </Badge>
          </dt>
          <dd className="mt-1 text-sm text-slate-600">
            {!near ? (
              <>{c.cameraSide.reason} Arm shape is not measured without it.</>
            ) : near.supportedPct !== null ? (
              <>
                <p>
                  Where the pose model put the {near.arm} elbow and wrist, as
                  shares of the swim. A point from the model is not proof the
                  arm was visible there.
                </p>
                <ul className="mt-2 space-y-1">
                  <li>
                    <span className="font-medium text-slate-900 tabular-nums">
                      {pct(near.supportedPct)}
                    </span>{" "}
                    backed by a followed underwater pull ({near.pulls}{" "}
                    {near.pulls === 1 ? "pull" : "pulls"}). Only these are
                    measured.
                  </li>
                  <li>
                    <span className="font-medium text-slate-900 tabular-nums">
                      {pct(near.modelOnlyPct ?? 0)}
                    </span>{" "}
                    model&apos;s guess only: the arm was in the air, hidden, or
                    not in a followed pull
                    {near.modelOnlyInFrontPct
                      ? ` (${pct(near.modelOnlyInFrontPct)} of the swim drawn stretched in front, which is not confirmed)`
                      : ""}
                    . Not measured.
                  </li>
                  <li>
                    <span className="font-medium text-slate-900 tabular-nums">
                      {pct(near.interpolatedPct ?? 0)}
                    </span>{" "}
                    filled in across short gaps. Not measured.
                  </li>
                  <li>
                    <span className="font-medium text-slate-900 tabular-nums">
                      {pct((near.rejectedPct ?? 0) + (near.missingPct ?? 0))}
                    </span>{" "}
                    rejected or missing.
                  </li>
                </ul>
              </>
            ) : (
              <>
                The {near.arm} arm was followed through {near.pulls} underwater{" "}
                {near.pulls === 1 ? "pull" : "pulls"} ({pct(near.followedPct)}{" "}
                of the swim). Outside those pulls the pose model&apos;s arm
                points can&apos;t be checked and are not used.
              </>
            )}
          </dd>
        </div>
        <div>
          <dt className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
            Stroke cycles
            <Badge tone={cycleStatusTone[c.cycles.status]}>
              {cycleStatusLabel[c.cycles.status]}
            </Badge>
          </dt>
          <dd className="mt-1 text-sm text-slate-600">
            {c.cycles.note}
            {c.cycles.partial > 0
              ? ` ${c.cycles.partial} part-${c.cycles.partial === 1 ? "cycle" : "cycles"} at the clip's edges ${c.cycles.partial === 1 ? "is" : "are"} not counted.`
              : ""}
          </dd>
        </div>
        <div>
          <dt className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
            Measurements
            <Badge tone={measured > 0 ? "sky" : "slate"}>
              {measured} of {measured + c.metricsUnavailable} made
            </Badge>
          </dt>
          <dd className="mt-1 text-sm text-slate-600">
            {c.metricsReliable} passed their own checks, {c.metricsLimited}{" "}
            {c.metricsLimited === 1 ? "is" : "are"} limited,{" "}
            {c.metricsUnavailable} could not be measured. Each one says why
            below.
          </dd>
        </div>
      </dl>
    </Card>
  );
}

const partLabels: [string, string][] = [
  ["head", "Head"],
  ["trunk", "Shoulders and hips"],
  ["arms", "Elbows and wrists"],
  ["legs", "Knees and ankles"],
  ["hands", "Hands"],
  ["feet", "Feet"],
];

function QualityCard({ quality }: { quality: QualityReport }) {
  const t = quality.tracking;
  const pct = (v: number) => `${Math.round(v)}%`;
  return (
    <Card title="Following the swimmer: details">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={gradeTone[quality.grade]}>
          {gradeLabel[quality.grade]}
        </Badge>
        <span className="text-sm text-slate-600">
          Usable pose in {pct(quality.validPosePct)} of {quality.analyzedFrames}{" "}
          frames
        </span>
      </div>
      <ul className="mb-4 space-y-1 text-sm text-slate-600">
        {quality.gradeReasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        {(
          [
            ["Placed by the model", quality.observedPct],
            ["Filled in (short gaps)", quality.interpolatedPct],
            ["Rejected", quality.rejectedPct],
            ["Missing", quality.missingPct],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="mt-0.5 text-sm font-medium text-slate-900 tabular-nums">
              {pct(value)}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-1 text-xs text-slate-500">
        Share of arm and leg joints across the clip. &quot;Placed by the
        model&quot; means the model&apos;s point was kept, not that the joint
        was visible.
      </p>

      <p className="mt-4 mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase">
        How much of each body part was tracked
      </p>
      <ul className="space-y-1.5">
        {partLabels
          .filter(([key]) => key in quality.bodyPartCoverage)
          .map(([key, label]) => {
            const value = quality.bodyPartCoverage[key];
            return (
              <li key={key} className="flex items-center gap-3 text-sm">
                <span className="w-36 shrink-0 text-slate-600">{label}</span>
                <span
                  className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200"
                  role="img"
                  aria-label={`${label}: ${pct(value)}`}
                >
                  <span
                    className="block h-full rounded-full bg-sky-600"
                    style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                  />
                </span>
                <span className="w-10 text-right text-slate-900 tabular-nums">
                  {pct(value)}
                </span>
              </li>
            );
          })}
      </ul>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-slate-500">
            Longest stretch without a pose
          </dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-900 tabular-nums">
            {quality.longestMissingSeconds.toFixed(1)} s
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">
            Swimmer found by the detector
          </dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-900 tabular-nums">
            {t.recorded && t.detectedPct !== null
              ? pct(t.detectedPct)
              : "Not recorded"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">
            Frames following someone else
          </dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-900 tabular-nums">
            {pct(t.otherSwimmerPct)}
          </dd>
        </div>
      </dl>

      {quality.filmingLimitations.length > 0 && (
        <div className="mt-4 rounded-xl bg-slate-50 p-3">
          <p className="mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">
            Limits of this kind of video
          </p>
          <ul className="space-y-1 text-sm text-slate-600">
            {quality.filmingLimitations.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
