"use client";

import { useEffect, useState, type ReactNode } from "react";

// Speedometer-style arc that sweeps up to `value` (0 to 100) when the page opens.
export function ArcGauge({
  value,
  label,
  children,
}: {
  value: number;
  label: string;
  children?: ReactNode;
}) {
  const id = `arc-${label.replace(/\W+/g, "-")}`;
  const pct = Math.max(0, Math.min(100, value));
  // Start empty, then fill on the next frame so the sweep animates (see .arc-fill).
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  // 240 degree arc, open at the bottom
  const arc = "M 22.4 81.4 A 44 44 0 1 1 97.6 81.4";
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className="relative mx-auto w-full max-w-[180px]"
    >
      <svg viewBox="0 0 120 96" className="w-full" aria-hidden="true">
        <defs>
          <linearGradient id={`${id}-fill`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#0284c7" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <path
          d={arc}
          pathLength={100}
          fill="none"
          strokeWidth="11"
          strokeLinecap="round"
          className="stroke-slate-200"
        />
        <path
          d={arc}
          pathLength={100}
          fill="none"
          stroke={`url(#${id}-fill)`}
          strokeWidth="11"
          strokeLinecap="round"
          strokeDasharray="100"
          strokeDashoffset={filled ? 100 - pct : 100}
          className="arc-fill"
        />
      </svg>
      <div className="absolute inset-x-0 top-[38%] text-center">{children}</div>
    </div>
  );
}
