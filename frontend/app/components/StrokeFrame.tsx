// Example annotated frame: an overhead view of a freestyle swimmer with the pose
// keypoints, the body's centre line, and where the hand entered vs. where it should.
// `bare` drops the pool background and legend so it can sit on a larger stage;
// `overlay={false}` hides the analysis markings and shows just the swimmer.
export function StrokeFrame({
  bare = false,
  overlay = true,
}: {
  bare?: boolean;
  overlay?: boolean;
}) {
  const joint = "fill-white stroke-sky-900";
  return (
    <figure className={bare ? "h-full w-full" : undefined}>
      <svg
        viewBox={bare ? "40 15 375 195" : "0 0 400 225"}
        className={bare ? "h-full w-full" : "h-auto w-full rounded-xl"}
        role="img"
        aria-label="Overhead frame: the left hand enters across the centre line instead of at shoulder width"
      >
        <defs>
          <linearGradient id="pool" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#0c4a6e" />
            <stop offset="100%" stopColor="#155e75" />
          </linearGradient>
        </defs>
        {!bare && (
          <>
            <rect width="400" height="225" fill="url(#pool)" />
            {/* Pool floor tiles and lane ropes */}
            {Array.from({ length: 9 }, (_, i) => (
              <line
                key={i}
                x1={i * 50}
                x2={i * 50}
                y1="0"
                y2="225"
                stroke="#ffffff"
                strokeOpacity="0.05"
              />
            ))}
            {[18, 207].map((y) => (
              <line
                key={y}
                x1="0"
                x2="400"
                y1={y}
                y2={y}
                stroke="#67e8f9"
                strokeOpacity="0.5"
                strokeWidth="4"
                strokeDasharray="10 6"
              />
            ))}
          </>
        )}

        {overlay && (
          <>
            {/* Centre line */}
            <line
              x1="20"
              x2="390"
              y1="112"
              y2="112"
              stroke="#ffffff"
              strokeOpacity="0.55"
              strokeDasharray="6 6"
            />
            <text x="48" y="106" className="fill-white/70 text-[10px]">
              centre line
            </text>

            {/* Target entry */}
            <path
              d="M275 90 L320 88 L360 88"
              fill="none"
              stroke="#2dd4bf"
              strokeWidth="2.5"
              strokeDasharray="5 4"
            />
            <circle cx="360" cy="88" r="9" fill="none" stroke="#2dd4bf" strokeWidth="2" />
          </>
        )}

        {/* Body */}
        <g stroke="#e0f2fe" strokeWidth="5" strokeLinecap="round" fill="none">
          <path d="M275 90 L275 134 L175 124 L175 100 Z" fill="#e0f2fe" fillOpacity="0.15" />
          <path d="M175 100 L115 98 L60 96" />
          <path d="M175 124 L115 128 L62 130" />
          <path d="M275 134 L238 152 L200 142" />
        </g>
        {/* Left arm, crossing over */}
        <path
          d="M275 90 L320 98 L362 120"
          fill="none"
          stroke={overlay ? "#fbbf24" : "#e0f2fe"}
          strokeWidth="5"
          strokeLinecap="round"
        />
        <circle cx="300" cy="112" r="15" fill="#e0f2fe" />

        {overlay && (
          <>
            {/* Keypoints */}
            {[
              [275, 90],
              [275, 134],
              [175, 100],
              [175, 124],
              [115, 98],
              [115, 128],
              [60, 96],
              [62, 130],
              [238, 152],
              [200, 142],
              [320, 98],
            ].map(([cx, cy]) => (
              <circle
                key={`${cx}-${cy}`}
                cx={cx}
                cy={cy}
                r="3.5"
                className={joint}
                strokeWidth="1.5"
              />
            ))}
            <circle cx="362" cy="120" r="5" fill="#fbbf24" stroke="#fff" strokeWidth="1.5" />

            {/* Callout */}
            <g>
              <line x1="362" y1="126" x2="340" y2="170" stroke="#fbbf24" strokeWidth="1.5" />
              <rect x="250" y="170" width="140" height="26" rx="6" fill="#fbbf24" />
              <text
                x="320"
                y="187"
                textAnchor="middle"
                className="fill-slate-900 text-[11px] font-semibold"
              >
                Hand crosses centre line
              </text>
            </g>
          </>
        )}
      </svg>
      {!bare && (
        <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-600">
          <span className="inline-flex items-center gap-2">
            <span className="h-1 w-5 rounded bg-amber-400" /> Your left arm
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-0 w-5 border-t-2 border-dashed border-teal-400" /> Target entry
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full border border-sky-900 bg-white" /> Tracked
            joints
          </span>
        </figcaption>
      )}
    </figure>
  );
}
