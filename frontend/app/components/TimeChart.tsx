import { formatDate, formatTime, type TimeEntry } from "@/app/lib/mock";

// Swim times over time. Faster times sit higher, so improvement reads as a rising line.
export function TimeChart({
  entries,
  goal,
  compact = false,
}: {
  entries: TimeEntry[];
  goal?: number;
  compact?: boolean;
}) {
  const width = 640;
  const height = compact ? 180 : 280;
  const pad = { top: 16, right: 16, bottom: compact ? 24 : 32, left: compact ? 8 : 52 };

  const times = entries.map((e) => e.seconds).concat(goal ?? []);
  const min = Math.min(...times);
  const max = Math.max(...times);
  const span = Math.max(max - min, 0.5);
  const lo = min - span * 0.15;
  const hi = max + span * 0.15;

  const start = new Date(entries[0].date).getTime();
  const end = new Date(entries[entries.length - 1].date).getTime();
  const x = (iso: string) =>
    pad.left +
    ((new Date(iso).getTime() - start) / Math.max(end - start, 1)) * (width - pad.left - pad.right);
  const y = (sec: number) => pad.top + ((sec - lo) / (hi - lo)) * (height - pad.top - pad.bottom);

  const line = entries.map((e, i) => `${i ? "L" : "M"}${x(e.date)},${y(e.seconds)}`).join(" ");
  const area = `${line} L${x(entries[entries.length - 1].date)},${height - pad.bottom} L${x(entries[0].date)},${height - pad.bottom} Z`;
  const ticks = [0, 1, 2, 3].map((i) => lo + ((hi - lo) * (i + 0.5)) / 4);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Times from ${formatTime(entries[0].seconds)} to ${formatTime(entries[entries.length - 1].seconds)}`}
    >
      <defs>
        <linearGradient id="water" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {!compact &&
        ticks.map((t) => (
          <g key={t}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(t)}
              y2={y(t)}
              className="stroke-slate-200"
              strokeDasharray="4 6"
            />
            <text
              x={pad.left - 10}
              y={y(t) + 4}
              textAnchor="end"
              className="fill-slate-500 text-[12px]"
            >
              {formatTime(t)}
            </text>
          </g>
        ))}

      {goal !== undefined && (
        <g>
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={y(goal)}
            y2={y(goal)}
            stroke="#14b8a6"
            strokeWidth="1.5"
            strokeDasharray="6 5"
          />
          <text
            x={width - pad.right}
            y={y(goal) - 6}
            textAnchor="end"
            className="fill-teal-600 text-[12px] font-medium"
          >
            Goal {formatTime(goal)}
          </text>
        </g>
      )}

      <path d={area} fill="url(#water)" />
      <path
        d={line}
        fill="none"
        className="stroke-sky-600"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />

      {entries.map((e) => (
        <circle
          key={e.date}
          cx={x(e.date)}
          cy={y(e.seconds)}
          r={e.meet ? 5.5 : 4}
          className={e.meet ? "fill-indigo-600 stroke-surface" : "fill-surface stroke-sky-600"}
          strokeWidth="2"
        >
          <title>{`${formatDate(e.date)}: ${formatTime(e.seconds)}${e.meet ? " (meet)" : ""}`}</title>
        </circle>
      ))}

      {[entries[0], entries[entries.length - 1]].map((e, i) => (
        <text
          key={e.date}
          x={x(e.date)}
          y={height - 6}
          textAnchor={i ? "end" : "start"}
          className="fill-slate-500 text-[12px]"
        >
          {formatDate(e.date)}
        </text>
      ))}
    </svg>
  );
}
