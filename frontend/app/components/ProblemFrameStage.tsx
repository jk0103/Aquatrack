"use client";

import { useState } from "react";

import {
  GaugeTile,
  LaneProgress,
  MainFix,
  PillRow,
  PoolBackdrop,
  RateGauge,
  RoundButton,
  WaterGauge,
} from "@/app/components/FeedbackStage";
import { Badge } from "@/app/components/ui";
import type { AnalysisV1, MetricV1 } from "@/app/lib/analysisV1";
import type { FeedbackItem } from "@/app/lib/feedback";
import { formatClock, type ProblemFrame } from "@/app/lib/problemFrames";
import type { LoadedFrames } from "@/app/lib/problemFramesLoad";
import type { VideoRecord } from "@/app/lib/videos";

// The real result in the example page's layout (/feedback/a-1042): the pool-blue stage with
// the floating card, but the drawn swimmer is replaced by still frames from the swimmer's
// own video, chosen by the backend for the feedback's priorities (lib/problemFrames.ts).
// Every number comes from the stored analysis; anything it did not measure is left out.

const ENTER_STAGGER_MS = 60; // the example's feedback-list stagger
const ENTER_MS = 350; // feedback-enter duration in globals.css

function metric(a: AnalysisV1, key: string): MetricV1 | null {
  const m = a.metrics.find((x) => x.key === key);
  return m && m.value !== null && m.status !== "unavailable" ? m : null;
}

const statusTone = { reliable: "teal", limited: "amber", unavailable: "slate" } as const;
const statusText = { reliable: "Reliable", limited: "Limited", unavailable: "Not measured" };
const gradeTone = { good: "teal", limited: "amber", insufficient: "slate" } as const;
const gradeText = { good: "Good", limited: "Limited", insufficient: "Too little" };

// Pills: only what this analysis measured. No score, lap, distance per stroke, breaths or
// kick: none of those is measured.
export function measuredPills(a: AnalysisV1): [string, string][] {
  const out: [string, string][] = [];
  const rate = metric(a, "stroke_rate");
  if (rate?.value != null) out.push(["Stroke rate", `${rate.value.toFixed(1)}/min`]);
  const cycle = metric(a, "cycle_duration");
  if (cycle?.value != null) out.push(["Cycle", `${cycle.value.toFixed(2)} s`]);
  const count = metric(a, "cycle_count");
  if (count?.value != null) out.push(["Cycles", `${Math.round(count.value)}`]);
  return out;
}

export function ResultPills({ analysis }: { analysis: AnalysisV1 }) {
  const pills = measuredPills(analysis);
  return pills.length ? <PillRow pills={pills} /> : null;
}

export function ProblemFrameStage({
  video,
  analysis,
  mainFix,
  frames,
  videoUrl,
  onPlayFrom,
}: {
  video: VideoRecord;
  analysis: AnalysisV1;
  mainFix: FeedbackItem | null;
  frames: LoadedFrames | null | undefined; // undefined while loading
  videoUrl: string | null;
  onPlayFrom: (t: number) => void;
}) {
  const [overlay, setOverlay] = useState(true);
  const [cardOpen, setCardOpen] = useState(true);
  const [selected, setSelected] = useState(0);
  const shown = frames?.frames ?? [];
  const current = shown[Math.min(selected, shown.length - 1)];

  const note =
    frames === undefined
      ? null
      : !mainFix
        ? "No main fix to show in this clip"
        : !shown.length
          ? "Not enough clear frames to show this"
          : null;

  return (
    <>
      <section
        aria-label="Your swim"
        className="relative overflow-hidden rounded-3xl bg-gradient-to-b from-sky-800 to-cyan-800 shadow-sm"
      >
        <PoolBackdrop />

        <div className="relative aspect-[4/3] w-full sm:aspect-[16/8] lg:aspect-auto lg:h-[560px]">
          {/* Frames sit where the example's swimmer does, to the right of the card */}
          <div className="absolute inset-y-4 right-14 left-2 sm:right-16 lg:top-10 lg:bottom-8 lg:left-[41%] lg:right-20">
            {current ? (
              <div className="flex h-full flex-col gap-2 sm:gap-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded-full bg-white/90 px-2.5 py-1 font-display text-sm font-semibold text-slate-900 tabular-nums dark:bg-white/90 dark:text-[#0f172a]">
                    {formatClock(current.t)}
                    {current.cycleIndex > 0 && (
                      <span className="ml-1.5 font-sans text-xs font-medium text-[#475569]">
                        cycle {current.cycleIndex}
                      </span>
                    )}
                  </span>
                  {videoUrl && (
                    <button
                      type="button"
                      onClick={() => onPlayFrom(current.t)}
                      className="tap-target rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur transition hover:bg-white/30"
                    >
                      Play from here
                    </button>
                  )}
                </div>
                <div className="relative min-h-0 flex-1">
                  <AnnotatedFrame
                    key={current.image}
                    frame={current}
                    url={frames?.urls[current.image] ?? ""}
                    overlay={overlay}
                    delayMs={ENTER_MS}
                  />
                </div>
                {shown.length > 1 && (
                  <Filmstrip
                    frames={shown}
                    urls={frames?.urls ?? {}}
                    selected={selected}
                    onSelect={setSelected}
                  />
                )}
              </div>
            ) : (
              <div className="flex h-full flex-col gap-2">
                {note && (
                  <span className="self-start rounded-full bg-white/90 px-2.5 py-1 text-xs font-semibold text-[#0f172a]">
                    {note}
                  </span>
                )}
                {videoUrl ? (
                  <video
                    src={videoUrl}
                    controls
                    playsInline
                    preload="metadata"
                    aria-label={`${video.distance} ${video.stroke} video`}
                    className="min-h-0 w-full flex-1 rounded-2xl bg-black/30 object-contain"
                  />
                ) : (
                  <p className="flex flex-1 items-center justify-center text-sm text-white/80">
                    Video unavailable
                  </p>
                )}
              </div>
            )}
          </div>

          {current && (
            <div className="absolute right-2.5 bottom-2.5 flex flex-col gap-1.5 sm:right-4 sm:bottom-4 sm:gap-2">
              <RoundButton
                label={overlay ? "Hide markings" : "Show markings"}
                active={overlay}
                onClick={() => setOverlay(!overlay)}
              >
                <path d="m12 4 8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4" />
              </RoundButton>
            </div>
          )}

          {cardOpen ? (
            <div className="absolute top-5 bottom-5 left-5 hidden w-[min(39%,440px)] lg:block">
              <ResultStatsCard
                video={video}
                analysis={analysis}
                mainFix={mainFix}
                onClose={() => setCardOpen(false)}
              />
            </div>
          ) : (
            <button
              onClick={() => setCardOpen(true)}
              className="absolute top-5 left-5 hidden rounded-full bg-white px-4 py-2 text-sm font-semibold text-[#075985] shadow-lg lg:block"
            >
              Show stats
            </button>
          )}
        </div>
      </section>
      <div className="mt-2 mb-6 flex flex-wrap justify-between gap-2 px-1 text-xs text-slate-500">
        <span>
          {current
            ? `Frame ${selected + 1} of ${shown.length} from your video`
            : "Your video, no markings"}
        </span>
        {current && <span>{overlay ? "Arrows placed from this frame's pose" : "Markings hidden"}</span>}
      </div>

      <div className="mb-6 lg:hidden">
        <ResultStatsCard video={video} analysis={analysis} mainFix={mainFix} />
      </div>
    </>
  );
}

// One frame, drawn in an SVG the size of the image so arrows stay on the body points
// whatever size it is shown at. The callout uses the example's yellow highlight.
function AnnotatedFrame({
  frame,
  url,
  overlay,
  delayMs,
}: {
  frame: ProblemFrame;
  url: string;
  overlay: boolean;
  delayMs: number;
}) {
  const w = frame.width || 1280;
  const h = frame.height || 720;
  const k = w / 400; // the example's callout is drawn on a 400-unit-wide frame
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="feedback-enter h-full w-full"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`Frame at ${formatClock(frame.t)}: ${frame.arrows.map((a) => a.label).join("; ")}`}
    >
      <defs>
        <marker
          id={`head-${frame.frameIndex}`}
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="4"
          markerHeight="4"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 z" fill="#fbbf24" />
        </marker>
      </defs>
      <image href={url} width={w} height={h} preserveAspectRatio="xMidYMid meet" />
      {overlay &&
        frame.arrows.map((a, n) => {
          const [tx, ty] = [a.to[0] * w, a.to[1] * h];
          const [lx, ly] = [a.labelAt[0] * w, a.labelAt[1] * h];
          const boxW = (a.label.length * 5.9 + 18) * k;
          const boxH = 26 * k;
          const bx = Math.min(Math.max(lx - boxW / 2, 4 * k), w - boxW - 4 * k);
          const by = ly - boxH / 2;
          // Stop the line short of the joint dot so the arrowhead stays visible.
          const dx = tx - lx;
          const dy = ty - (ly > ty ? by : by + boxH);
          const len = Math.hypot(dx, dy) || 1;
          const end = Math.max(len - 9 * k, 0) / len;
          const sy = ly > ty ? by : by + boxH;
          return (
            <g
              key={n}
              className="feedback-enter"
              style={{ animationDelay: `${delayMs + n * ENTER_STAGGER_MS}ms` }}
            >
              <line
                x1={lx}
                y1={sy}
                x2={lx + dx * end}
                y2={sy + dy * end}
                stroke="#fbbf24"
                strokeWidth={1.5 * k}
                markerEnd={`url(#head-${frame.frameIndex})`}
              />
              <circle cx={tx} cy={ty} r={5 * k} fill="#fbbf24" stroke="#fff" strokeWidth={1.5 * k} />
              <rect x={bx} y={by} width={boxW} height={boxH} rx={6 * k} fill="#fbbf24" />
              <text
                x={bx + boxW / 2}
                y={by + boxH / 2 + 4 * k}
                textAnchor="middle"
                fontSize={11 * k}
                fontWeight={600}
                fill="#0f172a"
              >
                {a.label}
              </text>
            </g>
          );
        })}
    </svg>
  );
}

function Filmstrip({
  frames,
  urls,
  selected,
  onSelect,
}: {
  frames: ProblemFrame[];
  urls: Record<string, string>;
  selected: number;
  onSelect: (i: number) => void;
}) {
  return (
    <ol className="flex shrink-0 gap-1.5 overflow-x-auto sm:gap-2" aria-label="Frames">
      {frames.map((f, i) => (
        <li
          key={f.image}
          className="feedback-enter shrink-0"
          style={{ animationDelay: `${i * ENTER_STAGGER_MS}ms` }}
        >
          <button
            type="button"
            onClick={() => onSelect(i)}
            aria-pressed={i === selected}
            aria-label={`Frame at ${formatClock(f.t)}`}
            className={`block overflow-hidden rounded-lg ring-2 transition duration-300 ${
              i === selected ? "ring-amber-400" : "ring-white/20 hover:ring-white/60"
            }`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- signed Storage link */}
            <img
              src={urls[f.image]}
              alt=""
              className="h-12 w-20 object-cover sm:h-16 sm:w-28"
              loading="lazy"
            />
          </button>
        </li>
      ))}
    </ol>
  );
}

// The example's floating card, filled from the real analysis. A block is left out when the
// analysis has nothing measured for it.
function ResultStatsCard({
  video,
  analysis,
  mainFix,
  onClose,
}: {
  video: VideoRecord;
  analysis: AnalysisV1;
  mainFix: FeedbackItem | null;
  onClose?: () => void;
}) {
  const rate = metric(analysis, "stroke_rate");
  const clip = analysis.clipDuration;
  const followed =
    analysis.swimStart !== null && analysis.swimEnd !== null && clip > 0
      ? Math.max(0, analysis.swimEnd - analysis.swimStart)
      : null;
  const pct = followed !== null ? Math.min(100, Math.round((followed / clip) * 100)) : 0;
  const tracked = Math.round(analysis.quality.validPosePct);
  return (
    <div className="flex h-full flex-col gap-3 rounded-2xl bg-surface p-4 shadow-xl ring-1 ring-sky-900/5">
      <div className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-sky-100 text-sky-700">
          <svg
            viewBox="0 0 24 24"
            className="h-6 w-6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <circle cx="16" cy="6" r="2" />
            <path d="m4 13 5-3 3 2 4-3M2 18c2 0 2-1.5 4-1.5S8 18 10 18s2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-semibold text-slate-900">
            {[video.distance, video.stroke].filter(Boolean).join(" ")}
          </p>
          <p className="text-sm text-slate-500">
            {video.camera}
            {clip > 0 ? ` · ${clip.toFixed(1)} s clip` : ""}
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Hide stats"
            className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        )}
      </div>

      {followed !== null && (
        <LaneProgress
          title="Swimming followed"
          value={`${followed.toFixed(1)} s`}
          pct={pct}
          left={`From ${formatClock(analysis.swimStart ?? 0)}`}
          right={`to ${formatClock(analysis.swimEnd ?? 0)}`}
        />
      )}

      <div className={`grid flex-1 gap-3 ${rate ? "grid-cols-2" : "grid-cols-1"}`}>
        {rate?.value != null && (
          <GaugeTile
            title="Stroke rate"
            badge={<Badge tone={statusTone[rate.status]}>{statusText[rate.status]}</Badge>}
          >
            <RateGauge value={Math.round(rate.value)} />
          </GaugeTile>
        )}
        <GaugeTile
          title="Tracking"
          badge={
            <Badge tone={gradeTone[analysis.quality.grade]}>
              {gradeText[analysis.quality.grade]}
            </Badge>
          }
        >
          <WaterGauge
            value={tracked}
            caption="% pose found"
            label={`Pose found in ${tracked}% of frames`}
          />
        </GaugeTile>
      </div>

      {mainFix && <MainFix issue={mainFix} />}
    </div>
  );
}
