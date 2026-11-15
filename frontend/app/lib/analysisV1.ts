// Analysis results v1.x, as the backend stores them (src/aquatrack/contracts.py, AnalysisResult).
//
// One document per run at videos/{videoId}/analyses/{analysisId}, written only by the backend.
// 1.0 (Phase 1) holds basic stroke timing and a tracking quality report. 1.1 adds `metrics`
// (each with its own reliability) and `coverage`. Older documents are never rewritten: a 1.0
// result simply has no metrics and is shown the way it always was.
// No posture scores, issues or corrections: anything not measured is listed with the reason.

export type QualityGrade = "good" | "limited" | "insufficient";

export type Unavailable = { key: string; label: string; reason: string };

export type MeasurementV1 = {
  key: string;
  label: string;
  value: number;
  unit: string;
  basis: string;
};

export type StrokeCycleV1 = {
  arm: "left" | "right";
  start: number; // seconds into the video
  end: number;
  duration: number;
  trusted: boolean;
  reason: string;
  kind: string; // 1.1: "merged" | "fragment" | "hidden" | ""
};

export type MetricStatus = "reliable" | "limited" | "unavailable";
export type MetricGroup = "timing" | "body" | "arm" | "consistency";

export type MetricSample = {
  t: number; // seconds into the video: a moment that shows this value
  value: number;
  start: number | null;
  end: number | null;
  label: string;
};

// One measurement with its own evidence. Definitions: docs/BIOMECHANICS_METRICS.md.
export type MetricV1 = {
  key: string;
  label: string;
  group: MetricGroup;
  kind: string;
  unit: string;
  description: string;
  status: MetricStatus;
  value: number | null;
  low: number | null;
  high: number | null;
  cycles: number;
  excludedCycles: number; // 1.2: left out because of the camera view
  coveragePct: number | null;
  side: string | null;
  samples: MetricSample[];
  basis: string;
  reason: string;
  limitations: string[];
};

export type ArmObservation = {
  arm: "left" | "right";
  cameraSide: boolean;
  pulls: number;
  pullsFollowedBack: number;
  followedPct: number;
  // 1.2: exactly one class per frame, adding up to 100. null in 1.1 results.
  supportedPct: number | null; // model points inside a followed underwater pull: what is measured
  interpolatedPct: number | null; // filled across a short gap
  modelOnlyPct: number | null; // placed by the model with nothing to back it up
  rejectedPct: number | null;
  missingPct: number | null;
  modelOnlyInFrontPct: number | null; // part of modelOnly: drawn stretched ahead, not confirmed
  modelOnlyCollapsedPct: number | null; // part of modelOnly: a segment drawn impossibly short
  // 1.1 fields (overlapping; kept for old results)
  inFrontPct: number;
  unverifiedPct: number;
  notObservedPct: number;
};

// What the analysis could stand behind, level by level. Tracking is only the first level.
export type Coverage = {
  trackingGrade: QualityGrade;
  cameraSide: {
    arm: "left" | "right" | null;
    evidence: string[];
    reason: string;
  };
  arms: ArmObservation[];
  cycles: {
    arm: string | null;
    detected: number;
    reliable: number;
    ambiguous: number;
    partial: number;
    countMeasurable: boolean;
    status: "complete" | "partial" | "none";
    note: string;
  };
  metricsReliable: number;
  metricsLimited: number;
  metricsUnavailable: number;
  // 1.2: did the camera keep a steady view. Not a measured angle; null in older results.
  view: {
    status: "steady" | "changing" | "unknown";
    smallestSizeShare: number | null;
    cyclesLeftOut: number;
    cyclesChecked: number;
    note: string;
  } | null;
  summary: string;
};

export type QualityReport = {
  totalFrames: number;
  analyzedFrames: number;
  validPosePct: number;
  observedPct: number;
  interpolatedPct: number;
  rejectedPct: number;
  missingPct: number;
  bodyPartCoverage: Record<string, number>;
  longestMissingSeconds: number;
  tracking: {
    recorded: boolean;
    detectedPct: number | null;
    carriedPct: number | null;
    noBoxPct: number | null;
    otherSwimmerPct: number;
    identityBreaks: number;
  };
  reliableStrokeCycles: number;
  grade: QualityGrade;
  gradeReasons: string[];
  filmingLimitations: string[];
};

export type AnalysisV1 = {
  schemaVersion: string;
  engineVersion: string;
  createdAt: Date | null;
  poseSource: string;
  models: {
    detector: string | null;
    pose: string;
    imgsz: number | null;
    confidence: number | null;
  };
  stroke: {
    measurable: boolean;
    reason: string;
    cycleCount: { left: number; right: number };
    cycles: StrokeCycleV1[];
  };
  swimStart: number | null;
  swimEnd: number | null;
  clipDuration: number;
  measurements: MeasurementV1[];
  unavailable: Unavailable[];
  quality: QualityReport;
  metrics: MetricV1[]; // empty for 1.0 results
  coverage: Coverage | null; // null for 1.0 results
};

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null =>
  v && typeof v === "object" ? (v as Obj) : null;
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const grades: QualityGrade[] = ["good", "limited", "insufficient"];
const statuses: MetricStatus[] = ["reliable", "limited", "unavailable"];
const groups: MetricGroup[] = ["timing", "body", "arm", "consistency"];
const arm = (v: unknown): "left" | "right" | null =>
  v === "left" || v === "right" ? v : null;

function parseMetric(raw: unknown): MetricV1[] {
  const o = obj(raw);
  const status = statuses.find((x) => x === o?.status);
  const group = groups.find((x) => x === o?.group);
  if (!o || !status || !group || !str(o.key)) return [];
  const value = num(o.value);
  // A metric without a number is never shown as measured, whatever its status says.
  const safe: MetricStatus = value === null ? "unavailable" : status;
  return [
    {
      key: str(o.key),
      label: str(o.label),
      group,
      kind: str(o.kind),
      unit: str(o.unit),
      description: str(o.description),
      status: safe,
      value: safe === "unavailable" ? null : value,
      low: num(o.low),
      high: num(o.high),
      cycles: num(o.n_cycles) ?? 0,
      excludedCycles: num(o.excluded_cycles) ?? 0,
      coveragePct: num(o.coverage_pct),
      side: str(o.side) || null,
      samples: list(o.samples).flatMap((x): MetricSample[] => {
        const sample = obj(x);
        const t = num(sample?.t_s);
        const v = num(sample?.value);
        return sample && t !== null && v !== null
          ? [
              {
                t,
                value: v,
                start: num(sample.start_s),
                end: num(sample.end_s),
                label: str(sample.label),
              },
            ]
          : [];
      }),
      basis: str(o.basis),
      reason: str(o.reason),
      limitations: list(o.limitations).map(str).filter(Boolean),
    },
  ];
}

function parseView(raw: unknown): Coverage["view"] {
  const v = obj(raw);
  const status = (["steady", "changing", "unknown"] as const).find(
    (x) => x === v?.status,
  );
  if (!v || !status) return null;
  return {
    status,
    smallestSizeShare: num(v.smallest_size_share),
    cyclesLeftOut: num(v.cycles_left_out) ?? 0,
    cyclesChecked: num(v.cycles_checked) ?? 0,
    note: str(v.note),
  };
}

function parseCoverage(raw: unknown): Coverage | null {
  const c = obj(raw);
  const cycles = obj(c?.cycles);
  const grade = grades.find((g) => g === c?.tracking_grade);
  if (!c || !cycles || !grade) return null;
  const side = obj(c.camera_side) ?? {};
  const status = (["complete", "partial", "none"] as const).find(
    (x) => x === cycles.status,
  );
  return {
    trackingGrade: grade,
    cameraSide: {
      arm: arm(side.arm),
      evidence: list(side.evidence).map(str).filter(Boolean),
      reason: str(side.reason),
    },
    arms: list(c.arms).flatMap((x): ArmObservation[] => {
      const a = obj(x);
      const which = arm(a?.arm);
      return a && which
        ? [
            {
              arm: which,
              cameraSide: a.camera_side === true,
              pulls: num(a.pulls) ?? 0,
              pullsFollowedBack: num(a.pulls_followed_back) ?? 0,
              followedPct: num(a.followed_pct) ?? 0,
              supportedPct: num(a.supported_pct),
              interpolatedPct: num(a.interpolated_pct),
              modelOnlyPct: num(a.model_only_pct),
              rejectedPct: num(a.rejected_pct),
              missingPct: num(a.missing_pct),
              modelOnlyInFrontPct: num(a.model_only_in_front_pct),
              modelOnlyCollapsedPct: num(a.model_only_collapsed_pct),
              inFrontPct: num(a.in_front_pct) ?? 0,
              unverifiedPct: num(a.unverified_pct) ?? 0,
              notObservedPct: num(a.not_observed_pct) ?? 0,
            },
          ]
        : [];
    }),
    cycles: {
      arm: str(cycles.arm) || null,
      detected: num(cycles.detected) ?? 0,
      reliable: num(cycles.reliable) ?? 0,
      ambiguous: num(cycles.ambiguous) ?? 0,
      partial: num(cycles.partial) ?? 0,
      countMeasurable: cycles.count_measurable === true,
      status: status ?? "none",
      note: str(cycles.note),
    },
    metricsReliable: num(c.metrics_reliable) ?? 0,
    metricsLimited: num(c.metrics_limited) ?? 0,
    metricsUnavailable: num(c.metrics_unavailable) ?? 0,
    view: parseView(c.view),
    summary: str(c.summary),
  };
}

// Reads an analysis document. Returns null unless it is a v1 result with a quality report,
// so a half-written or newer-format document never shows up as numbers on the page.
export function parseAnalysisV1(raw: unknown): AnalysisV1 | null {
  const a = obj(raw);
  const q = obj(a?.quality);
  const stroke = obj(a?.stroke);
  if (!a || !q || !stroke || !str(a.schema_version).startsWith("1."))
    return null;
  const grade = grades.find((g) => g === q.grade);
  if (!grade) return null;
  const tracking = obj(q.tracking) ?? {};
  const timing = obj(a.timing) ?? {};
  const config = obj(a.config);
  const counts = obj(stroke.cycle_count) ?? {};
  const parts: Record<string, number> = {};
  for (const [name, value] of Object.entries(obj(q.body_part_coverage) ?? {})) {
    const pct = num(value);
    if (pct !== null) parts[name] = pct;
  }
  const created = Date.parse(str(a.created_at));
  return {
    schemaVersion: str(a.schema_version),
    engineVersion: str(a.engine_version),
    createdAt: Number.isNaN(created) ? null : new Date(created),
    poseSource: str(a.pose_source),
    models: {
      detector: str(obj(a.detector)?.name) || null,
      pose: str(obj(a.pose)?.name),
      imgsz: num(config?.detector_imgsz),
      confidence: num(config?.detector_confidence),
    },
    stroke: {
      measurable: stroke.measurable === true,
      reason: str(stroke.reason),
      cycleCount: {
        left: num(counts.left) ?? 0,
        right: num(counts.right) ?? 0,
      },
      cycles: list(stroke.cycles).flatMap((c): StrokeCycleV1[] => {
        const o = obj(c);
        const start = num(o?.start_s);
        const end = num(o?.end_s);
        if (
          !o ||
          start === null ||
          end === null ||
          (o.arm !== "left" && o.arm !== "right")
        )
          return [];
        return [
          {
            arm: o.arm,
            start,
            end,
            duration: num(o.duration_s) ?? end - start,
            trusted: o.trusted === true,
            reason: str(o.reason),
            kind: str(o.kind),
          },
        ];
      }),
    },
    swimStart: num(timing.swim_start_s),
    swimEnd: num(timing.swim_end_s),
    clipDuration: num(timing.clip_duration_s) ?? 0,
    measurements: list(a.measurements).flatMap((m): MeasurementV1[] => {
      const o = obj(m);
      const value = num(o?.value);
      if (!o || value === null || !str(o.key)) return [];
      return [
        {
          key: str(o.key),
          label: str(o.label),
          value,
          unit: str(o.unit),
          basis: str(o.basis),
        },
      ];
    }),
    unavailable: list(a.unavailable).flatMap((u): Unavailable[] => {
      const o = obj(u);
      return o && str(o.key)
        ? [{ key: str(o.key), label: str(o.label), reason: str(o.reason) }]
        : [];
    }),
    quality: {
      totalFrames: num(q.total_frames) ?? 0,
      analyzedFrames: num(q.analyzed_frames) ?? 0,
      validPosePct: num(q.valid_pose_pct) ?? 0,
      observedPct: num(q.observed_pct) ?? 0,
      interpolatedPct: num(q.interpolated_pct) ?? 0,
      rejectedPct: num(q.rejected_pct) ?? 0,
      missingPct: num(q.missing_pct) ?? 0,
      bodyPartCoverage: parts,
      longestMissingSeconds: num(q.longest_missing_s) ?? 0,
      tracking: {
        recorded: tracking.recorded === true,
        detectedPct: num(tracking.detected_pct),
        carriedPct: num(tracking.carried_pct),
        noBoxPct: num(tracking.no_box_pct),
        otherSwimmerPct: num(tracking.other_swimmer_pct) ?? 0,
        identityBreaks: num(tracking.identity_breaks) ?? 0,
      },
      reliableStrokeCycles: num(q.reliable_stroke_cycles) ?? 0,
      grade,
      gradeReasons: list(q.grade_reasons).map(str).filter(Boolean),
      filmingLimitations: list(q.filming_limitations).map(str).filter(Boolean),
    },
    metrics: list(a.metrics).flatMap(parseMetric),
    coverage: parseCoverage(a.coverage),
  };
}

// The number alone; the unit is shown next to it.
export function formatNumber(m: MeasurementV1): string {
  return Number.isInteger(m.value)
    ? `${m.value}`
    : m.value.toFixed(m.value < 10 ? 2 : 1);
}

// A metric value in its own unit's precision (the backend already rounded it).
export function formatMetric(value: number, unit: string): string {
  if (unit === "cycles") return `${Math.round(value)}`;
  const digits =
    unit === "deg" || unit === "cycles/min" || unit === "%" ? 1 : 2;
  const text = value.toFixed(digits);
  return Number(text) === 0 ? (0).toFixed(digits) : text; // never "-0.0"
}

export const unitLabel: Record<string, string> = {
  deg: "°",
  "trunk lengths": "trunk lengths",
  "cycles/min": "cycles/min",
};

export const statusLabel: Record<MetricStatus, string> = {
  reliable: "Passed its checks",
  limited: "Limited",
  unavailable: "Not measurable",
};

export const statusTone = {
  reliable: "teal",
  limited: "amber",
  unavailable: "slate",
} as const;

export const groupTitle: Record<MetricGroup, string> = {
  timing: "Stroke timing",
  body: "Body position",
  arm: "Arm pull",
  consistency: "Consistency",
};

export const gradeLabel: Record<QualityGrade, string> = {
  good: "Good tracking",
  limited: "Limited tracking",
  insufficient: "Not enough to measure",
};

export const gradeTone = {
  good: "teal",
  limited: "amber",
  insufficient: "slate",
} as const;
