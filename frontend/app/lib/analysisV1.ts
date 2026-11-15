// Analysis results v1, as the backend stores them (src/aquatrack/contracts.py, AnalysisResult).
//
// One document per run at videos/{videoId}/analyses/{analysisId}, written only by the backend.
// v1 holds basic stroke timing and a quality report. It has no posture scores, issues or
// corrections: anything not measured is listed in `unavailable` with the reason.

import { doc, getDoc } from "firebase/firestore";

import { db } from "@/app/lib/firebase";

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
  models: { detector: string | null; pose: string; imgsz: number | null; confidence: number | null };
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
};

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null => (v && typeof v === "object" ? (v as Obj) : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const grades: QualityGrade[] = ["good", "limited", "insufficient"];

// Reads an analysis document. Returns null unless it is a v1 result with a quality report,
// so a half-written or newer-format document never shows up as numbers on the page.
export function parseAnalysisV1(raw: unknown): AnalysisV1 | null {
  const a = obj(raw);
  const q = obj(a?.quality);
  const stroke = obj(a?.stroke);
  if (!a || !q || !stroke || !str(a.schema_version).startsWith("1.")) return null;
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
      cycleCount: { left: num(counts.left) ?? 0, right: num(counts.right) ?? 0 },
      cycles: list(stroke.cycles).flatMap((c): StrokeCycleV1[] => {
        const o = obj(c);
        const start = num(o?.start_s);
        const end = num(o?.end_s);
        if (!o || start === null || end === null || (o.arm !== "left" && o.arm !== "right"))
          return [];
        return [
          {
            arm: o.arm,
            start,
            end,
            duration: num(o.duration_s) ?? end - start,
            trusted: o.trusted === true,
            reason: str(o.reason),
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
        { key: str(o.key), label: str(o.label), value, unit: str(o.unit), basis: str(o.basis) },
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
  };
}

// One analysis run of the swimmer's own video, or null if it's missing or not readable.
export async function loadAnalysis(videoId: string, analysisId: string): Promise<AnalysisV1 | null> {
  const snap = await getDoc(doc(db, "videos", videoId, "analyses", analysisId));
  return snap.exists() ? parseAnalysisV1(snap.data()) : null;
}

// The number alone; the unit is shown next to it.
export function formatNumber(m: MeasurementV1): string {
  return Number.isInteger(m.value) ? `${m.value}` : m.value.toFixed(m.value < 10 ? 2 : 1);
}

export const gradeLabel: Record<QualityGrade, string> = {
  good: "Good tracking",
  limited: "Limited tracking",
  insufficient: "Not enough to measure",
};

export const gradeTone = { good: "teal", limited: "amber", insufficient: "slate" } as const;
