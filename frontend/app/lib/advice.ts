// Hybrid advice for one analysis, as the backend writes it (src/aquatrack/contracts.py,
// Advice). One document at videos/{videoId}/advice/{adviceId}; an existing one is never
// replaced. Three kinds of content that are never mixed:
//   observations / consistent  what the measurements show (checked against them)
//   suggestions                an AI model's coaching ideas: to try, never confirmed faults
//   generalPractice            library activities that do not depend on a detected problem
// `source` "deterministic" means no AI answer was used; the page then shows the existing
// feedback and only the general practice from here.
// Pure parsing: no Firebase.

export type AdviceStatement = { statement: string; evidenceRefs: string[]; timesS: number[] };

export type AdviceSuggestion = {
  id: string;
  title: string;
  category: string;
  noticed: string;
  whyItMayMatter: string;
  tryThis: string;
  drillId: string;
  drillName: string;
  drillHow: string;
  checkNextTime: string;
  confidence: "low" | "medium" | "high";
  cyclesSupporting: number;
  evidenceRefs: string[];
  timesS: number[];
  // Decided by the backend's checks from the sample itself (few cycles, frame-limited
  // timing), not by the model.
  tentative: boolean;
  tentativeReasons: string[];
  // "exploratory": rests on raw joint positions that are not a verified measurement.
  evidenceBasis: "measured" | "exploratory";
};

export type AdvicePractice = {
  activityId: string;
  name: string;
  purpose: string;
  instructions: string[];
  reason: string;
};

export type Advice = {
  version: string;
  source: "ai" | "deterministic";
  fallbackReason: string;
  model: string;
  trustedCycles: number;
  summary: string;
  dataQuality: string[];
  observations: AdviceStatement[];
  consistent: AdviceStatement[];
  suggestions: AdviceSuggestion[];
  generalPractice: AdvicePractice[];
  limitations: string[];
  createdAt: string;
};

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
const numbers = (v: unknown): number[] =>
  Array.isArray(v) ? v.filter((x): x is number => typeof x === "number" && Number.isFinite(x)) : [];
const records = (v: unknown): Record<string, unknown>[] =>
  Array.isArray(v)
    ? v.filter((x): x is Record<string, unknown> => typeof x === "object" && x !== null)
    : [];

function statements(v: unknown): AdviceStatement[] {
  return records(v)
    .map((s) => ({
      statement: str(s.statement),
      evidenceRefs: strings(s.evidence_refs),
      timesS: numbers(s.times_s),
    }))
    .filter((s) => s.statement);
}

// Null when the document is not advice this page can show.
export function parseAdvice(raw: unknown): Advice | null {
  if (typeof raw !== "object" || raw === null) return null;
  const d = raw as Record<string, unknown>;
  const version = str(d.advice_version);
  if (!version.startsWith("1.")) return null;
  const source = d.source === "ai" ? "ai" : d.source === "deterministic" ? "deterministic" : null;
  if (!source) return null;
  const suggestions = records(d.suggestions)
    .map((s, n) => ({
      id: str(s.id) || `s${n + 1}`,
      title: str(s.title),
      category: str(s.category),
      noticed: str(s.noticed),
      whyItMayMatter: str(s.why_it_may_matter),
      tryThis: str(s.try_this),
      drillId: str(s.drill_id),
      drillName: str(s.drill_name),
      drillHow: str(s.drill_how),
      checkNextTime: str(s.check_next_time),
      confidence: (["low", "medium", "high"].includes(str(s.confidence))
        ? str(s.confidence)
        : "low") as AdviceSuggestion["confidence"],
      cyclesSupporting: typeof s.cycles_supporting === "number" ? s.cycles_supporting : 0,
      evidenceRefs: strings(s.evidence_refs),
      timesS: numbers(s.times_s),
      tentative: s.tentative === true,
      evidenceBasis: (s.evidence_basis === "exploratory" ? "exploratory" : "measured") as AdviceSuggestion["evidenceBasis"],
      tentativeReasons: strings(s.tentative_reasons),
    }))
    .filter((s) => s.title && s.noticed)
    .slice(0, 3);
  return {
    version,
    source,
    fallbackReason: str(d.fallback_reason),
    model: str(d.model),
    trustedCycles: typeof d.trusted_cycles === "number" ? d.trusted_cycles : 0,
    summary: str(d.summary),
    dataQuality: strings(d.data_quality),
    observations: statements(d.observations),
    consistent: statements(d.consistent),
    // An AI suggestion is only ever shown from a document the checks marked as AI advice.
    suggestions: source === "ai" ? suggestions : [],
    generalPractice: records(d.general_practice)
      .map((p) => ({
        activityId: str(p.activity_id),
        name: str(p.name),
        purpose: str(p.purpose),
        instructions: strings(p.instructions),
        reason: str(p.reason),
      }))
      .filter((p) => p.name),
    limitations: strings(d.limitations),
    createdAt: str(d.created_at),
  };
}

const CATEGORY_LABEL: Record<string, string> = {
  timing: "Rhythm and timing",
  arm_path: "Arm pull",
  body_alignment: "Body position",
  legs: "Legs and kick",
  head: "Head position",
  breathing: "Breathing",
  other: "Other",
};
export const categoryLabel = (c: string): string => CATEGORY_LABEL[c] ?? "Other";

// Evidence references are internal names; show something a swimmer can read.
export function evidenceLabel(ref: string): string {
  const last = ref.split(".").pop() ?? ref;
  return last
    .replace(/_(s|deg)$/, "")
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase());
}

// The headline of a result: what kind of evidence it has, in words that don't overstate it.
//   a confirmed priority from the measurement rules -> its title (passed in)
//   AI suggestions only -> suggestions to try, not a diagnosis
//   neither -> nothing established, which is a normal result
export function resultHeadline(
  priorityTitle: string | null,
  advice: Advice | null,
): { title: string; note: string } {
  const n = advice?.suggestions.length ?? 0;
  if (priorityTitle)
    return {
      title: priorityTitle,
      note:
        n > 0
          ? "This pattern was measured in your video. The AI suggestions below are separate ideas to try."
          : "This pattern was measured in your video.",
    };
  if (n > 0)
    return {
      title: n === 1 ? "One thing to try from this swim" : `${n} things to try from this swim`,
      note:
        "The measurements alone don't establish a technique fault. An AI model read how you moved and suggests what to try next. These are suggestions, not a diagnosis.",
    };
  return {
    title: "No clear technique issue in this clip",
    note: "Nothing in the measurements points to something you need to fix, which is a normal result. General practice is below.",
  };
}
