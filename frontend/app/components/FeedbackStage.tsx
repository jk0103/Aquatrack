"use client";

import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import { StrokeFrame } from "@/app/components/StrokeFrame";
import { Badge } from "@/app/components/ui";
import { feedback, swimMetrics, type Analysis, type FeedbackPoint } from "@/app/lib/mock";

// Feedback page layout borrowed from a fleet dashboard: the video is the "map", with a
// floating stats card, a rotation dial and round player buttons laid over it.

const severityTone = { Focus: "amber", Watch: "sky", Good: "teal" } as const;
const filters = ["All", "Focus", "Watch", "Good"] as const;
type Filter = (typeof filters)[number];

export function StatPills({ analysis }: { analysis: Analysis }) {
  const m = swimMetrics;
  const pills = [
    ["Score", `${analysis.score}`],
    ["Lap", m.lapTime],
    ["Stroke rate", `${m.strokeRate}/min`],
    ["Per stroke", `${m.distancePerStroke} m`],
    ["Breaths", `${m.breaths}`],
    ["Kick", m.kick],
  ];
  return (
    <ul className="flex gap-2 overflow-x-auto pt-1 pb-2">
      {pills.map(([label, value]) => (
        <li
          key={label}
          className="group relative flex shrink-0 cursor-default items-center gap-1.5 overflow-hidden rounded-full border border-slate-200 bg-surface px-3.5 py-1.5 text-sm shadow-sm transition duration-300 ease-out hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-50 hover:shadow-md hover:shadow-sky-900/10"
        >
          {/* A soft ripple of light sweeps across on hover */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/2 -skew-x-12 bg-gradient-to-r from-transparent via-white/80 to-transparent opacity-0 transition-[left,opacity] duration-700 ease-out group-hover:left-full group-hover:opacity-100"
          />
          <span className="relative text-slate-500 transition-colors duration-300 group-hover:text-sky-700">
            {label}
          </span>
          <span className="relative font-semibold text-slate-900 transition-colors duration-300 group-hover:text-sky-900">
            {value}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function FeedbackStage({ analysis, aside }: { analysis: Analysis; aside: ReactNode }) {
  const [playing, setPlaying] = useState(false);
  const [slow, setSlow] = useState(false);
  const [overlay, setOverlay] = useState(true);
  const [cardOpen, setCardOpen] = useState(true);
  const [filter, setFilter] = useState<Filter>("All");

  const focus = feedback.find((f) => f.severity === "Focus");
  const shown = feedback.filter((f) => filter === "All" || f.severity === filter);
  const count = (f: Filter) =>
    f === "All" ? feedback.length : feedback.filter((p) => p.severity === f).length;

  return (
    <>
      {/* Stage */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-b from-sky-800 to-cyan-800 shadow-sm">
        <PoolBackdrop />

        <div className="relative aspect-[4/3] w-full sm:aspect-[16/8] lg:aspect-auto lg:h-[560px]">
          {/* Swimmer sits to the right of the card on wide screens */}
          <div className="absolute inset-y-4 right-14 left-2 sm:right-16 lg:top-10 lg:bottom-8 lg:left-[41%] lg:right-20">
            <StrokeFrame bare overlay={overlay} />
          </div>

          <span className="absolute top-3 left-3 rounded-full bg-black/30 px-2.5 py-1 text-xs font-medium text-white lg:hidden">
            {swimMetrics.clock} · {swimMetrics.atMeters} m
          </span>

          <RotationDial degrees={swimMetrics.rotationDeg} />

          {/* Player buttons */}
          <div className="absolute right-2.5 bottom-2.5 flex flex-col gap-1.5 sm:right-4 sm:bottom-4 sm:gap-2">
            <RoundButton label={playing ? "Pause" : "Play"} onClick={() => setPlaying(!playing)}>
              {playing ? (
                <path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor" stroke="none" />
              ) : (
                <path d="M8 5.5v13l10-6.5z" fill="currentColor" stroke="none" />
              )}
            </RoundButton>
            <RoundButton
              label={slow ? "Normal speed" : "Slow motion"}
              active={slow}
              onClick={() => setSlow(!slow)}
            >
              <text
                x="12"
                y="16"
                textAnchor="middle"
                fontSize="9"
                fontWeight="700"
                fill="currentColor"
                stroke="none"
              >
                {slow ? "½×" : "1×"}
              </text>
            </RoundButton>
            <RoundButton label="Next frame">
              <path d="M6 6v12l8-6zM16 6h2v12h-2z" fill="currentColor" stroke="none" />
            </RoundButton>
            <RoundButton
              label={overlay ? "Hide markings" : "Show markings"}
              active={overlay}
              onClick={() => setOverlay(!overlay)}
            >
              <path d="m12 4 8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4" />
            </RoundButton>
            <RoundButton label="Full screen">
              <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
            </RoundButton>
          </div>

          {/* Floating card on wide screens */}
          {cardOpen ? (
            <div className="absolute top-5 bottom-5 left-5 hidden w-[min(39%,440px)] lg:block">
              <StatsCard analysis={analysis} focus={focus} onClose={() => setCardOpen(false)} />
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
        <span>Space to play or pause · ← → to step frames</span>
        <span>{overlay ? "Markings from pose tracking" : "Markings hidden"}</span>
      </div>

      {/* Card stacks under the video on phones and tablets */}
      <div className="mb-6 lg:hidden">
        <StatsCard analysis={analysis} focus={focus} />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <section className="rounded-2xl glass p-5 sm:p-6 lg:col-span-3">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold text-slate-900">Feedback</h2>
            <FilterTabs value={filter} onChange={setFilter} count={count} />
          </div>
          <ol key={filter} className="space-y-5">
            {shown.map((point, i) => (
              <li
                key={point.title}
                className="feedback-enter"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <FeedbackItem point={point} n={feedback.indexOf(point) + 1} />
              </li>
            ))}
          </ol>
          {analysis.comment && (
            <blockquote className="mt-6 rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
              <p className="mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">
                Your comment
              </p>
              “{analysis.comment}”
            </blockquote>
          )}
        </section>
        <div className="lg:col-span-2">{aside}</div>
      </div>
    </>
  );
}

function StatsCard({
  analysis,
  focus,
  onClose,
}: {
  analysis: Analysis;
  focus?: FeedbackPoint;
  onClose?: () => void;
}) {
  const m = swimMetrics;
  const pct = Math.round((m.atMeters / m.lapMeters) * 100);
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
          <div className="flex items-center gap-2">
            <p className="truncate text-lg font-semibold text-slate-900">
              {analysis.distance} {analysis.stroke}
            </p>
            <Badge tone="teal">Analyzed</Badge>
          </div>
          <p className="text-sm text-slate-500">
            {analysis.camera} · {m.clock} of {m.lapTime}
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Hide stats"
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
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

      {/* Lane progress */}
      <div className="rounded-xl bg-slate-50 p-3">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-slate-800">Wall → {m.lapMeters} m</span>
          <span className="text-slate-500">
            <span className="font-semibold text-slate-900">{m.atMeters} m</span> {pct}%
          </span>
        </div>
        <div className="relative mt-2 h-2.5 overflow-hidden rounded-full bg-sky-100">
          <div
            className="h-full rounded-full bg-gradient-to-r from-sky-600 to-cyan-400"
            style={{ width: `${pct}%` }}
          />
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-[repeating-linear-gradient(90deg,transparent_0_10px,rgba(255,255,255,0.5)_10px_12px)]"
          />
        </div>
        <div className="mt-2 flex justify-between text-xs text-slate-500">
          <span>25 m split {m.split25}</span>
          <span>Lap {m.lapTime}</span>
        </div>
      </div>

      {/* Gauges */}
      <div className="grid flex-1 grid-cols-2 gap-3">
        <div className="flex flex-col rounded-xl bg-slate-50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">Stroke rate</span>
            <Badge tone="teal">In range</Badge>
          </div>
          <RateGauge value={m.strokeRate} target={m.strokeRateTarget} />
        </div>
        <div className="flex flex-col rounded-xl bg-slate-50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">Technique</span>
            <Badge tone="sky">+4</Badge>
          </div>
          <WaterGauge value={analysis.score} />
        </div>
      </div>

      {focus && (
        <div className="flex items-start gap-2.5 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
          <svg
            viewBox="0 0 24 24"
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M12 3 2 21h20zm-1 6h2v6h-2zm0 8h2v2h-2z" />
          </svg>
          <span>
            <span className="font-semibold">Main fix:</span> {focus.title}
          </span>
        </div>
      )}
    </div>
  );
}

// Speedometer-style gauge, 0 to 70 strokes per minute, with the target band marked.
function RateGauge({ value, target }: { value: number; target: [number, number] }) {
  const max = 70;
  const start = 135;
  const sweep = 270;
  const angle = (v: number) => ((start + (v / max) * sweep) * Math.PI) / 180;
  const point = (v: number, r: number) => [
    50 + r * Math.cos(angle(v)),
    50 + r * Math.sin(angle(v)),
  ];
  const arc = (from: number, to: number, r: number) => {
    const [x1, y1] = point(from, r);
    const [x2, y2] = point(to, r);
    const large = ((to - from) / max) * sweep > 180 ? 1 : 0;
    return `M${x1} ${y1} A${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  };
  const [nx, ny] = point(value, 30);
  return (
    <div className="flex flex-1 flex-col items-center justify-center">
      <svg
        viewBox="0 0 100 88"
        className="w-full max-w-[150px]"
        role="img"
        aria-label={`${value} strokes per minute`}
      >
        <path
          d={arc(0, max, 40)}
          fill="none"
          className="stroke-slate-200"
          strokeWidth="7"
          strokeLinecap="round"
        />
        <path d={arc(target[0], target[1], 40)} fill="none" stroke="#2dd4bf" strokeWidth="7" />
        <path
          d={arc(0, value, 40)}
          fill="none"
          stroke="#0284c7"
          strokeWidth="3"
          strokeLinecap="round"
        />
        {[0, 10, 20, 30, 40, 50, 60, 70].map((t) => {
          const [x1, y1] = point(t, 31);
          const [x2, y2] = point(t, 34);
          const [tx, ty] = point(t, 24);
          return (
            <g key={t}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} className="stroke-slate-400" strokeWidth="1" />
              <text x={tx} y={ty + 2} textAnchor="middle" fontSize="5.5" className="fill-slate-400">
                {t}
              </text>
            </g>
          );
        })}
        <line
          x1="50"
          y1="50"
          x2={nx}
          y2={ny}
          className="stroke-slate-900"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <circle cx="50" cy="50" r="3.5" className="fill-slate-900" />
        <text x="50" y="84" textAnchor="middle" fontSize="11" fontWeight="700" className="fill-slate-900">
          {value}/min
        </text>
      </svg>
    </div>
  );
}

// Round tank that fills with water to the score. The water rises on load, then two wave
// layers drift past each other and a few bubbles float up (animations in globals.css).
function WaterGauge({ value }: { value: number }) {
  // The card can render twice (laptop and phone layouts), so SVG ids must be unique.
  const id = useId();
  const level = 86 - (value / 100) * 72; // y of the water surface inside the circle
  // One wave period is 50 units; the path is 4 periods long so sliding it by 50 loops cleanly.
  const wave = (y: number, amp: number) =>
    `M-50 ${y} Q-37.5 ${y - amp} -25 ${y} T0 ${y} T25 ${y} T50 ${y} T75 ${y} T100 ${y} T125 ${y} T150 ${y} V120 H-50 Z`;
  return (
    <div className="flex flex-1 flex-col items-center justify-center">
      <svg
        viewBox="0 0 100 100"
        className="w-full max-w-[130px]"
        role="img"
        aria-label={`Technique score ${value}`}
      >
        <defs>
          <clipPath id={`${id}-circle`}>
            <circle cx="50" cy="50" r="36" />
          </clipPath>
          <linearGradient id={`${id}-water`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#0369a1" />
          </linearGradient>
        </defs>
        <circle
          cx="50"
          cy="50"
          r="42"
          fill="none"
          className="stroke-slate-200"
          strokeWidth="4"
          strokeDasharray="2 3"
        />
        <circle cx="50" cy="50" r="36" className="fill-slate-50" />
        <g clipPath={`url(#${id}-circle)`}>
          <g className="water-rise" style={{ "--rise": `${100 - level}px` } as CSSProperties}>
            <g className="water-bob">
              {/* Back wave: lighter, slower, drifting the other way */}
              <path
                className="wave-slide wave-slide-back"
                d={wave(level - 2, 3)}
                fill="#7dd3fc"
                opacity="0.6"
              />
              <path className="wave-slide" d={wave(level, 4)} fill={`url(#${id}-water)`} />
            </g>
            {[
              [38, 0],
              [57, 1.4],
              [47, 2.6],
            ].map(([cx, delay]) => (
              <circle
                key={cx}
                className="water-bubble"
                cx={cx}
                cy="84"
                r="1.6"
                fill="#e0f2fe"
                style={{ animationDelay: `${delay}s` }}
              />
            ))}
          </g>
        </g>
        <text
          x="50"
          y="47"
          textAnchor="middle"
          fontSize="20"
          fontWeight="700"
          className={value > 55 ? "fill-white" : "fill-slate-900"}
        >
          {value}
        </text>
        <text
          x="50"
          y="60"
          textAnchor="middle"
          fontSize="7"
          className={value > 45 ? "fill-sky-50/90" : "fill-slate-500"}
        >
          out of 100
        </text>
      </svg>
    </div>
  );
}

// Compass-like dial for body rotation, top right of the stage.
function RotationDial({ degrees }: { degrees: number }) {
  return (
    <div className="absolute top-4 right-4 hidden h-28 w-28 rounded-full bg-white/90 p-2 shadow-lg ring-4 ring-white/30 sm:block lg:h-36 lg:w-36">
      <svg
        viewBox="0 0 100 100"
        className="h-full w-full"
        role="img"
        aria-label={`Body rotation ${degrees} degrees`}
      >
        {Array.from({ length: 36 }, (_, i) => {
          const a = (i * 10 * Math.PI) / 180;
          const long = i % 3 === 0;
          return (
            <line
              key={i}
              x1={50 + 44 * Math.sin(a)}
              y1={50 - 44 * Math.cos(a)}
              x2={50 + (long ? 38 : 41) * Math.sin(a)}
              y2={50 - (long ? 38 : 41) * Math.cos(a)}
              stroke={long ? "#0369a1" : "#94a3b8"}
              strokeWidth={long ? 1.5 : 0.8}
            />
          );
        })}
        {/* Target range 35 to 45 degrees each side */}
        <path d="M50 50 L72.9 17.2 A40 40 0 0 1 78.3 21.7 Z" fill="#2dd4bf" opacity="0.35" />
        <g transform={`rotate(${degrees} 50 50)`}>
          <path d="M50 14 L54 50 L46 50 Z" fill="#f59e0b" />
          <path d="M50 86 L54 50 L46 50 Z" fill="#cbd5e1" />
        </g>
        <circle cx="50" cy="50" r="6" fill="#0f172a" />
        <text x="50" y="72" textAnchor="middle" fontSize="11" fontWeight="700" fill="#0f172a">
          {degrees}°
        </text>
        <text x="50" y="81" textAnchor="middle" fontSize="6" fill="#64748b">
          rotation
        </text>
      </svg>
    </div>
  );
}

function RoundButton({
  label,
  children,
  onClick,
  active = false,
}: {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`flex h-9 w-9 items-center sm:h-10 sm:w-10 justify-center rounded-full shadow-md transition ${
        active ? "bg-white text-[#075985]" : "bg-white/20 text-white backdrop-blur hover:bg-white/30"
      }`}
    >
      <svg
        viewBox="0 0 24 24"
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {children}
      </svg>
    </button>
  );
}

function PoolBackdrop() {
  return (
    <svg
      aria-hidden="true"
      className="absolute inset-0 h-full w-full"
      preserveAspectRatio="none"
      viewBox="0 0 100 100"
    >
      {Array.from({ length: 12 }, (_, i) => (
        <line
          key={i}
          x1={i * 9}
          x2={i * 9}
          y1="0"
          y2="100"
          stroke="#ffffff"
          strokeOpacity="0.05"
          strokeWidth="0.3"
        />
      ))}
      {[6, 94].map((y) => (
        <line
          key={y}
          x1="0"
          x2="100"
          y1={y}
          y2={y}
          stroke="#67e8f9"
          strokeOpacity="0.45"
          strokeWidth="1.2"
          strokeDasharray="3 2"
        />
      ))}
    </svg>
  );
}

function FeedbackItem({ point, n }: { point: FeedbackPoint; n: number }) {
  return (
    <div className="flex gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sm font-semibold text-sky-800">
        {n}
      </span>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-slate-900">{point.title}</p>
          <Badge tone={severityTone[point.severity]}>{point.severity}</Badge>
        </div>
        <p className="mt-1 text-sm text-slate-600">{point.detail}</p>
        <p className="mt-2 text-sm text-slate-700">
          <span className="font-medium text-teal-700">Drill: </span>
          {point.drill}
        </p>
      </div>
    </div>
  );
}

// Segmented filter with a white pill that slides to the chosen option.
function FilterTabs({
  value,
  onChange,
  count,
}: {
  value: Filter;
  onChange: (f: Filter) => void;
  count: (f: Filter) => number;
}) {
  const buttons = useRef<Partial<Record<Filter, HTMLButtonElement | null>>>({});
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const measure = () => {
      const el = buttons.current[value];
      if (el) setPill({ left: el.offsetLeft, width: el.offsetWidth });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [value]);

  return (
    <div
      className="relative flex max-w-full overflow-x-auto rounded-full bg-slate-100 p-1 text-sm"
      role="group"
      aria-label="Show"
    >
      {pill && (
        <span
          aria-hidden="true"
          className="absolute top-1 bottom-1 rounded-full bg-surface shadow-sm transition-[left,width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]"
          style={{ left: pill.left, width: pill.width }}
        />
      )}
      {filters.map((f) => {
        const on = value === f;
        return (
          <button
            key={f}
            ref={(el) => {
              buttons.current[f] = el;
            }}
            onClick={() => onChange(f)}
            aria-pressed={on}
            className={`group relative flex items-center gap-1.5 rounded-full px-3 py-1.5 font-medium transition-colors duration-300 ${
              on ? "text-slate-900" : "text-slate-500 hover:text-sky-800"
            } ${pill ? "" : on ? "bg-surface shadow-sm" : ""}`}
          >
            {/* Hover: a faint pill grows in behind the option you're pointing at */}
            {!on && (
              <span
                aria-hidden="true"
                className="absolute inset-0 scale-75 rounded-full bg-sky-100/80 opacity-0 transition duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-100 group-hover:opacity-100"
              />
            )}
            <span className="relative transition-transform duration-300 ease-out group-hover:-translate-y-px">
              {f}
            </span>
            <span
              className={`relative rounded-full px-1.5 text-xs transition duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] group-hover:scale-115 ${
                on
                  ? "bg-sky-700 text-white"
                  : "bg-slate-200 text-slate-600 group-hover:bg-sky-200 group-hover:text-sky-800"
              }`}
            >
              {count(f)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
