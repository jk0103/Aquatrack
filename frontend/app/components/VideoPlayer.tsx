"use client";

import { useRef, useState, type ReactNode } from "react";

import type { KeyFrame, StrokeCycle } from "@/app/lib/analysis";
import { formatDuration } from "@/app/lib/videos";

const FRAME = 1 / 30; // step size; most phone footage is 30 fps

// A real video with the browser's own controls, plus slow motion, frame steps and full
// screen in the stage's round-button style. Stroke cycles and key frames from an analysis,
// when there are any, show as a strip under the video; clicking a key frame jumps to it.
export function VideoPlayer({
  src,
  label,
  strokeCycles = [],
  keyFrames = [],
  durationHint,
}: {
  src: string;
  label: string;
  strokeCycles?: StrokeCycle[];
  keyFrames?: KeyFrame[];
  durationHint?: number;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [slow, setSlow] = useState(false);
  const [duration, setDuration] = useState(durationHint ?? 0);
  const [failed, setFailed] = useState(false);

  function step(frames: number) {
    const v = video.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.max(0, Math.min(v.duration || 0, v.currentTime + frames * FRAME));
  }

  function toggleSlow() {
    const v = video.current;
    if (v) v.playbackRate = slow ? 1 : 0.5;
    setSlow(!slow);
  }

  function seek(time: number) {
    const v = video.current;
    if (!v) return;
    v.pause();
    v.currentTime = time;
    v.focus();
  }

  function fullScreen() {
    const el = stage.current;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el?.requestFullscreen?.();
  }

  const markers = duration > 0 && (strokeCycles.length > 0 || keyFrames.length > 0);

  return (
    <div>
      <div ref={stage} className="relative overflow-hidden rounded-3xl bg-black shadow-sm">
        {failed ? (
          <div className="flex aspect-video flex-col items-center justify-center bg-gradient-to-b from-sky-800 to-cyan-900 px-6 text-center text-sm text-sky-50">
            <p className="font-semibold">This video can&apos;t play in this browser</p>
            <p className="mt-1 text-sky-100/80">
              Some phone videos (HEVC .mov) only play in Safari.{" "}
              <a href={src} className="underline" target="_blank" rel="noreferrer">
                Open the file
              </a>{" "}
              to watch it another way.
            </p>
          </div>
        ) : (
          <video
            ref={video}
            src={src}
            controls
            playsInline
            preload="metadata"
            aria-label={label}
            onLoadedMetadata={(e) => {
              const d = e.currentTarget.duration;
              if (Number.isFinite(d)) setDuration(d);
            }}
            onError={() => setFailed(true)}
            className="aspect-video max-h-[70vh] w-full bg-black object-contain"
          />
        )}
        {!failed && (
          <div className="absolute top-2.5 right-2.5 flex gap-1.5 sm:top-4 sm:right-4 sm:gap-2">
            <RoundButton label="Back one frame" onClick={() => step(-1)}>
              <path d="M18 6v12l-8-6zM8 6H6v12h2z" fill="currentColor" stroke="none" />
            </RoundButton>
            <RoundButton label="Forward one frame" onClick={() => step(1)}>
              <path d="M6 6v12l8-6zM16 6h2v12h-2z" fill="currentColor" stroke="none" />
            </RoundButton>
            <RoundButton
              label={slow ? "Normal speed" : "Slow motion"}
              active={slow}
              onClick={toggleSlow}
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
            <RoundButton label="Full screen" onClick={fullScreen}>
              <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
            </RoundButton>
          </div>
        )}
      </div>

      {markers && (
        <div className="mt-3">
          <div className="relative h-6 rounded-full bg-slate-200" aria-hidden="true">
            {strokeCycles.map((c, i) => (
              <span
                key={i}
                className={`absolute inset-y-1 rounded-full ${i % 2 ? "bg-sky-400/70" : "bg-cyan-500/70"}`}
                style={{
                  left: `${(c.start / duration) * 100}%`,
                  width: `${Math.max(0.5, ((c.end - c.start) / duration) * 100)}%`,
                }}
              />
            ))}
            {keyFrames.map((k) => (
              <span
                key={`${k.time}-${k.label}`}
                className="absolute top-0 bottom-0 w-0.5 bg-amber-500"
                style={{ left: `${(k.time / duration) * 100}%` }}
              />
            ))}
          </div>
          <p className="mt-1.5 text-xs text-slate-500">
            {strokeCycles.length > 0 && `${strokeCycles.length} stroke cycles`}
            {strokeCycles.length > 0 && keyFrames.length > 0 && " · "}
            {keyFrames.length > 0 && `${keyFrames.length} key frames`}
          </p>
          {keyFrames.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {keyFrames.map((k) => (
                <li key={`${k.time}-${k.label}`}>
                  <button
                    type="button"
                    onClick={() => seek(k.time)}
                    className="rounded-full border border-slate-200 bg-surface px-3 py-1.5 text-sm text-slate-700 shadow-sm transition hover:border-sky-300 hover:bg-sky-50"
                  >
                    <span className="font-semibold text-slate-900">{formatDuration(k.time)}</span>{" "}
                    {k.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function RoundButton({
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
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active || undefined}
      title={label}
      className={`tap-target flex h-9 w-9 items-center justify-center rounded-full shadow-md transition sm:h-10 sm:w-10 ${
        active
          ? "bg-white text-[#075985]"
          : "bg-black/35 text-white backdrop-blur hover:bg-black/50"
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
