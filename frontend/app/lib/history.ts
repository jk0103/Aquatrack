// Comparisons between a swimmer's own sessions and their progress over time, as the backend
// computes them from stored analyses (src/aquatrack/analysis/comparison.py). Nothing here is
// stored: each view is recomputed from the analyses it names. Pure code: no Firebase.
//
// The words are neutral on purpose. "Increased" and "decreased" say which way a number
// moved, never whether that is good.

export type ChangeState =
  | "increased"
  | "decreased"
  | "no_clear_change"
  | "insufficient_evidence"
  | "not_comparable";

export type MetricComparison = {
  metricKey: string;
  label: string;
  unit: string;
  state: ChangeState;
  previous: number | null;
  current: number | null;
  change: number | null;
  relativePct: number | null;
  threshold: number | null;
  reasons: string[];
  limitations: string[];
};

export type SessionSummary = {
  videoId: string;
  recordedAt: string;
  stroke: string;
  camera: string;
  distance: string;
  poolLength: string;
  schemaVersion: string;
  trackingGrade: string;
  viewStatus: string;
  strokeRate: number | null;
};

export type SessionComparison = {
  previous: SessionSummary;
  current: SessionSummary;
  comparable: boolean;
  sessionReasons: string[];
  metrics: MetricComparison[];
  summary: string;
};

export type ProgressPoint = {
  videoId: string;
  recordedAt: string;
  value: number;
  cycles: number;
};
export type ProgressMetric = {
  metricKey: string;
  label: string;
  unit: string;
  points: ProgressPoint[];
  overall: MetricComparison | null;
};
export type ProgressSeries = {
  key: string;
  stroke: string;
  camera: string;
  distance: string;
  sessions: SessionSummary[];
  metrics: ProgressMetric[];
};

export type FollowUpState =
  | "not_yet_evaluated"
  | "comparable_measurement_available"
  | "measurable_change_observed"
  | "no_clear_measurable_change"
  | "cannot_evaluate";
export type FollowUp = {
  checkpointId: string;
  title: string;
  sourceVideoId: string;
  state: FollowUpState;
  explanation: string;
};

export type ProgressView = {
  videos: number;
  analyzed: number;
  baseline: boolean;
  series: ProgressSeries[];
  notIncluded: { session: SessionSummary; reasons: string[] }[];
  repeatedLimitations: string[];
  note: string;
  history: {
    videoId: string;
    recordedAt: string;
    fileName: string;
    observations: number;
    issueCandidates: string[];
    priorities: string[];
  }[];
  latestVideoId: string | null;
  openCheckpoints: {
    id: string;
    title: string;
    whatToFilm: string;
    reason: string;
  }[];
  followups: FollowUp[];
};

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null =>
  v && typeof v === "object" ? (v as Obj) : null;
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strings = (v: unknown): string[] => list(v).map(str).filter(Boolean);
const states: ChangeState[] = [
  "increased",
  "decreased",
  "no_clear_change",
  "insufficient_evidence",
  "not_comparable",
];
const followStates: FollowUpState[] = [
  "not_yet_evaluated",
  "comparable_measurement_available",
  "measurable_change_observed",
  "no_clear_measurable_change",
  "cannot_evaluate",
];

function parseMetric(raw: unknown): MetricComparison[] {
  const m = obj(raw);
  const state = states.find((s) => s === m?.state);
  if (!m || !state || !str(m.metric_key)) return [];
  const moved =
    state === "increased" ||
    state === "decreased" ||
    state === "no_clear_change";
  return [
    {
      metricKey: str(m.metric_key),
      label: str(m.label),
      unit: str(m.unit),
      state,
      previous: num(m.previous),
      current: num(m.current),
      // A change is only a number when the two values could actually be compared.
      change: moved ? num(m.change) : null,
      relativePct: moved ? num(m.relative_pct) : null,
      threshold: moved ? num(m.threshold) : null,
      reasons: strings(m.reasons),
      limitations: strings(m.limitations),
    },
  ];
}

function parseSession(raw: unknown): SessionSummary {
  const s = obj(raw) ?? {};
  return {
    videoId: str(s.video_id),
    recordedAt: str(s.recorded_at),
    stroke: str(s.stroke),
    camera: str(s.camera),
    distance: str(s.distance),
    poolLength: str(s.pool_length),
    schemaVersion: str(s.schema_version),
    trackingGrade: str(s.tracking_grade),
    viewStatus: str(s.view_status),
    strokeRate: num(s.stroke_rate),
  };
}

export function parseComparison(raw: unknown): SessionComparison | null {
  const c = obj(raw);
  if (
    !c ||
    !str(c.comparison_version).startsWith("1.") ||
    !obj(c.previous) ||
    !obj(c.current)
  )
    return null;
  const metrics = list(c.metrics).flatMap(parseMetric);
  return {
    previous: parseSession(c.previous),
    current: parseSession(c.current),
    comparable: metrics.some((m) => m.change !== null),
    sessionReasons: strings(c.session_reasons),
    metrics,
    summary: str(c.summary),
  };
}

export function parseFollowUps(raw: unknown): FollowUp[] {
  return list(raw).flatMap((x): FollowUp[] => {
    const f = obj(x);
    const state = followStates.find((s) => s === f?.state);
    return f && state && str(f.title)
      ? [
          {
            checkpointId: str(f.checkpoint_id),
            title: str(f.title),
            sourceVideoId: str(f.source_video_id),
            state,
            explanation: str(f.explanation),
          },
        ]
      : [];
  });
}

export function parseProgress(raw: unknown): ProgressView | null {
  const top = obj(raw);
  const p = obj(top?.progress);
  if (!top || !p || !str(p.progress_version).startsWith("1.")) return null;
  const reasons = obj(p.not_included_reasons) ?? {};
  const series = list(p.series).flatMap((x): ProgressSeries[] => {
    const s = obj(x);
    if (!s) return [];
    const sessions = list(s.sessions).map(parseSession);
    const known = new Set(sessions.map((v) => v.videoId));
    return [
      {
        key: str(s.key),
        stroke: str(s.stroke),
        camera: str(s.camera),
        distance: str(s.distance),
        sessions,
        metrics: list(s.metrics).flatMap((y): ProgressMetric[] => {
          const m = obj(y);
          if (!m) return [];
          // A point must belong to a session of this series: nothing is drawn from elsewhere.
          const points = list(m.points).flatMap((z): ProgressPoint[] => {
            const pt = obj(z);
            const value = num(pt?.value);
            return pt && value !== null && known.has(str(pt.video_id))
              ? [
                  {
                    videoId: str(pt.video_id),
                    recordedAt: str(pt.recorded_at),
                    value,
                    cycles: num(pt.n_cycles ?? pt.cycles) ?? 0,
                  },
                ]
              : [];
          });
          return points.length
            ? [
                {
                  metricKey: str(m.metric_key),
                  label: str(m.label),
                  unit: str(m.unit),
                  points,
                  overall:
                    points.length >= 2
                      ? (parseMetric(m.overall)[0] ?? null)
                      : null,
                },
              ]
            : [];
        }),
      },
    ];
  });
  return {
    videos: num(p.videos) ?? 0,
    analyzed: num(p.analyzed) ?? 0,
    // A baseline unless some series really has two sessions, whatever the document says.
    baseline: !series.some((s) => s.sessions.length >= 2),
    series,
    notIncluded: list(p.not_in_any_series).map((x) => {
      const session = parseSession(x);
      return { session, reasons: strings(reasons[session.videoId]) };
    }),
    repeatedLimitations: strings(p.repeated_limitations),
    note: str(p.note),
    history: list(top.history).flatMap((x) => {
      const h = obj(x);
      return h
        ? [
            {
              videoId: str(h.video_id),
              recordedAt: str(h.recorded_at),
              fileName: str(h.file_name),
              observations: num(h.observations) ?? 0,
              issueCandidates: strings(h.issue_candidates),
              priorities: strings(h.priorities),
            },
          ]
        : [];
    }),
    latestVideoId: str(top.latest_video_id) || null,
    openCheckpoints: list(top.open_checkpoints).flatMap((x) => {
      const c = obj(x);
      return c && str(c.title)
        ? [
            {
              id: str(c.id),
              title: str(c.title),
              whatToFilm: str(c.what_to_film),
              reason: str(c.reason),
            },
          ]
        : [];
    }),
    followups: parseFollowUps(top.followups),
  };
}

export const stateLabel: Record<ChangeState, string> = {
  increased: "Increased",
  decreased: "Decreased",
  no_clear_change: "No clearly measurable change",
  insufficient_evidence: "Insufficient evidence",
  not_comparable: "Not comparable",
};
// One tone for both directions: a rise is not shown as good or a fall as bad.
export const stateTone = {
  increased: "indigo",
  decreased: "indigo",
  no_clear_change: "slate",
  insufficient_evidence: "slate",
  not_comparable: "slate",
} as const;

export const followUpLabel: Record<FollowUpState, string> = {
  not_yet_evaluated: "Not yet evaluated",
  comparable_measurement_available: "Comparable measurement available",
  measurable_change_observed: "Measurable change observed",
  no_clear_measurable_change: "No clear measurable change",
  cannot_evaluate: "Cannot evaluate from this video",
};

// Where to draw each point of a small trend chart. Points are spaced evenly in the order
// given (oldest first): two sessions a day apart and two a year apart are both "next".
export function chartPoints(
  values: number[],
  width: number,
  height: number,
  pad = 12,
): { x: number; y: number }[] {
  if (values.length === 0) return [];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  return values.map((v, i) => ({
    x:
      values.length === 1
        ? width / 2
        : pad + (i * (width - 2 * pad)) / (values.length - 1),
    y: hi === lo ? height / 2 : pad + ((hi - v) / span) * (height - 2 * pad),
  }));
}

// Records the swimmer typed in themselves, for one event: best time and the gap to a target.
export type RecordView = {
  event: string;
  pool: string;
  best: number;
  target: number | null;
  gap: number | null;
};
export function recordViews(
  pbs: { event: string; pool: string; seconds: number }[],
  target: { event: string; pool: string; seconds: number } | null,
): RecordView[] {
  return pbs
    .filter((p) => p.event && Number.isFinite(p.seconds))
    .map((p) => {
      // A target only applies to the same event in the same pool length.
      const same =
        target && target.event === p.event && target.pool === p.pool
          ? target.seconds
          : null;
      return {
        event: p.event,
        pool: p.pool,
        best: p.seconds,
        target: same,
        gap: same === null ? null : Math.round((p.seconds - same) * 100) / 100,
      };
    });
}

export function shortDate(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t)
    ? ""
    : new Date(t).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
}
