// Technique analysis results, as the web app expects to receive them.
//
// PROVISIONAL: the analysis engine (src/aquatrack/analysis/) is still being built and has no
// agreed output contract yet. These types describe what the UI can show; once the backend
// writes results, adjust `parseAnalysis` to its real shape. Until then nothing in Firestore
// matches, every upload shows "not analyzed yet", and the example feedback is labelled as such.
//
// Results are expected on the video's Firestore record as an `analysis` field, written by the
// backend (firestore.rules lets only the backend update video records).

import { feedback, swimMetrics, type FeedbackPoint } from "@/app/lib/mock";

export type Severity = "Focus" | "Watch" | "Good";

// One measured quantity. `value` is null when the engine couldn't measure it in this clip,
// and `reason` says why; the UI then shows "Not measured" instead of a number.
export type Measurement = {
  key: string;
  label: string;
  value: number | null;
  unit: string; // "strokes/min", "m", "°", "s", ""
  confidence?: number; // 0 to 1
  reason?: string;
};

export type StrokeCycle = { start: number; end: number }; // seconds into the video

export type KeyFrame = {
  time: number; // seconds into the video
  label: string;
  issueId?: string;
};

export type TechniqueIssue = {
  id: string;
  title: string;
  severity: Severity;
  detail: string;
  drill?: string;
  confidence?: number;
  keyFrames?: number[]; // seconds into the video
};

export type AnalysisResult = {
  videoId: string;
  engineVersion?: string;
  createdAt?: Date | null;
  strokeRate: Measurement | null;
  measurements: Measurement[];
  strokeCycles: StrokeCycle[];
  keyFrames: KeyFrame[];
  mainPriority: TechniqueIssue | null;
  issues: TechniqueIssue[]; // everything besides the main priority
  checkpoints: string[]; // what to check in the next video
};

const num = (v: unknown): number | undefined =>
  typeof v === "number" && Number.isFinite(v) ? v : undefined;
const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const obj = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === "object" ? (v as Record<string, unknown>) : null;

function parseMeasurement(raw: unknown): Measurement | null {
  const m = obj(raw);
  const key = str(m?.key);
  if (!m || !key) return null;
  return {
    key,
    label: str(m.label) ?? key,
    value: num(m.value) ?? null,
    unit: str(m.unit) ?? "",
    confidence: num(m.confidence),
    reason: str(m.reason),
  };
}

function parseIssue(raw: unknown, i: number): TechniqueIssue | null {
  const m = obj(raw);
  const title = str(m?.title);
  if (!m || !title) return null;
  const severity = (["Focus", "Watch", "Good"] as const).find((s) => s === m.severity) ?? "Watch";
  return {
    id: str(m.id) ?? `issue-${i}`,
    title,
    severity,
    detail: str(m.detail) ?? "",
    drill: str(m.drill),
    confidence: num(m.confidence),
    keyFrames: list(m.keyFrames)
      .map(num)
      .filter((t): t is number => t !== undefined),
  };
}

// Reads the `analysis` field of a video record. Returns null when it's missing or doesn't
// look like a result, so a half-written or differently shaped result never breaks the page.
export function parseAnalysis(videoId: string, raw: unknown): AnalysisResult | null {
  const a = obj(raw);
  if (!a) return null;
  const measurements = list(a.measurements)
    .map(parseMeasurement)
    .filter((m): m is Measurement => m !== null);
  const issues = list(a.issues)
    .map(parseIssue)
    .filter((m): m is TechniqueIssue => m !== null);
  const main = parseIssue(a.mainPriority, -1);
  if (!measurements.length && !issues.length && !main) return null;
  const created = obj(a.createdAt) as { toDate?: () => Date } | null;
  return {
    videoId,
    engineVersion: str(a.engineVersion),
    createdAt: typeof created?.toDate === "function" ? created.toDate() : null,
    strokeRate: parseMeasurement(a.strokeRate),
    measurements,
    strokeCycles: list(a.strokeCycles)
      .map(obj)
      .map((c) => ({ start: num(c?.start), end: num(c?.end) }))
      .filter((c): c is StrokeCycle => c.start !== undefined && c.end !== undefined),
    keyFrames: list(a.keyFrames).flatMap((raw): KeyFrame[] => {
      const k = obj(raw);
      const time = num(k?.time);
      if (time === undefined) return [];
      return [{ time, label: str(k?.label) ?? "Key frame", issueId: str(k?.issueId) }];
    }),
    mainPriority: main,
    issues,
    checkpoints: list(a.checkpoints)
      .map(str)
      .filter((s): s is string => Boolean(s)),
  };
}

export function formatMeasurement(m: Measurement): string {
  if (m.value === null) return "Not measured";
  const value = Number.isInteger(m.value) ? `${m.value}` : m.value.toFixed(m.value < 10 ? 2 : 1);
  if (!m.unit) return value;
  return m.unit === "°" ? `${value}°` : `${value} ${m.unit}`;
}

// All issues, main priority first, as the feedback list shows them.
export function allIssues(result: AnalysisResult): TechniqueIssue[] {
  return result.mainPriority ? [result.mainPriority, ...result.issues] : result.issues;
}

function fromFeedback(point: FeedbackPoint, i: number): TechniqueIssue {
  return { id: `example-${i}`, ...point };
}

// The sample result behind the example feedback pages, in the same shape as a real one.
// None of these numbers come from anyone's video.
export const exampleResult: AnalysisResult = {
  videoId: "example",
  strokeRate: {
    key: "stroke_rate",
    label: "Stroke rate",
    value: swimMetrics.strokeRate,
    unit: "strokes/min",
  },
  measurements: [
    {
      key: "distance_per_stroke",
      label: "Per stroke",
      value: swimMetrics.distancePerStroke,
      unit: "m",
    },
    { key: "breaths", label: "Breaths", value: swimMetrics.breaths, unit: "" },
    { key: "body_rotation", label: "Body rotation", value: swimMetrics.rotationDeg, unit: "°" },
  ],
  strokeCycles: [],
  keyFrames: [],
  mainPriority: fromFeedback(
    feedback.find((f) => f.severity === "Focus")!,
    0,
  ),
  issues: feedback.filter((f) => f.severity !== "Focus").map((f, i) => fromFeedback(f, i + 1)),
  checkpoints: [
    "Left hand enters at shoulder width, not past the centre line",
    "Head turns with the body roll, before the pull starts",
  ],
};
