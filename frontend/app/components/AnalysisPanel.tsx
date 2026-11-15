"use client";

import { useState } from "react";

import { Badge, Button, Card, LoadingState } from "@/app/components/ui";
import {
  formatNumber,
  gradeLabel,
  gradeTone,
  type AnalysisV1,
  type QualityReport,
} from "@/app/lib/analysisV1";
import { requestAnalysis, type VideoRecord } from "@/app/lib/videos";

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
            The analysis finished, but its results are in a format this page can&apos;t show.
          </p>
        </Card>
      );
    return <Results analysis={analysis} onSeek={onSeek} />;
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
        </div>
      )}
      {video.status === "uploaded" && (
        <>
          <p className="text-sm text-slate-600">This video hasn&apos;t been analyzed yet.</p>
          <div className="mt-4">
            <Button onClick={start} disabled={sending}>
              {sending ? "Starting…" : "Analyze this video"}
            </Button>
          </div>
        </>
      )}
      {failed && (
        <div role="alert">
          <p className="font-medium text-slate-900">The analysis couldn&apos;t finish.</p>
          <p className="mt-1 text-sm text-slate-600">
            {video.job?.errorMessage ?? "Something went wrong while analysing this video."}
          </p>
          <p className="mt-1 text-sm text-slate-600">Your upload is still saved.</p>
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
          Couldn&apos;t start the analysis. {sendError}
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
                {m.basis && <dd className="mt-0.5 text-xs text-slate-500">From {m.basis}</dd>}
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-slate-600">
            <span className="font-medium text-slate-900">Not measurable in this clip.</span>{" "}
            {stroke.reason}
          </p>
        )}
        {stroke.measurable && (
          <p className="mt-4 text-xs text-slate-500">
            One cycle is one full turn of one arm. Measured from{" "}
            {stroke.cycleCount.left + stroke.cycleCount.right} reliable cycles
            {skipped > 0 ? `; ${skipped} unclear ${skipped === 1 ? "cycle was" : "cycles were"} left out` : ""}
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
                    {i + 1} · {c.arm === "left" ? "L" : "R"} · {c.start.toFixed(1)} s
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
        {analysis.models.detector ? ` · detector ${analysis.models.detector}` : ""}
        {analysis.models.pose ? ` · pose ${analysis.models.pose}` : ""}
        {analysis.createdAt
          ? ` · ${analysis.createdAt.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
          : ""}
      </p>
    </div>
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
    <Card title="Tracking quality">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={gradeTone[quality.grade]}>{gradeLabel[quality.grade]}</Badge>
        <span className="text-sm text-slate-600">
          Usable pose in {pct(quality.validPosePct)} of {quality.analyzedFrames} frames
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
            ["Seen by the model", quality.observedPct],
            ["Estimated (short gaps)", quality.interpolatedPct],
            ["Rejected", quality.rejectedPct],
            ["Missing", quality.missingPct],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="mt-0.5 text-sm font-medium text-slate-900 tabular-nums">{pct(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-1 text-xs text-slate-500">Share of arm and leg joints across the clip.</p>

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
                <span className="w-10 text-right text-slate-900 tabular-nums">{pct(value)}</span>
              </li>
            );
          })}
      </ul>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-slate-500">Longest stretch without a pose</dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-900 tabular-nums">
            {quality.longestMissingSeconds.toFixed(1)} s
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Swimmer found by the detector</dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-900 tabular-nums">
            {t.recorded && t.detectedPct !== null ? pct(t.detectedPct) : "Not recorded"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Frames following someone else</dt>
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
