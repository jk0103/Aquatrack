// Feedback for one swim, as the backend writes it (src/aquatrack/contracts.py, Feedback).
// One document at videos/{videoId}/feedback/{feedbackId}; an existing one is never replaced.
//
// Five categories that are never mixed: observation (measured in the video), focus (may
// deserve attention), priority (ranked, at most three), education (general information for
// a chosen goal, NOT about the swimmer's video) and insufficient (could not be determined).
// Pure parsing: no Firebase.

import { parseFollowUps, type FollowUp } from "./history.ts";
import type { FindingEvidence, FindingSample } from "./interpretation.ts";

export type FeedbackCategory =
  "observation" | "focus" | "priority" | "education" | "insufficient";

export type FeedbackItem = {
  id: string;
  category: FeedbackCategory;
  personal: boolean;
  title: string;
  text: string; // validated rewording if there is one, else the deterministic text
  reworded: boolean;
  whyItMayMatter: string;
  evidence: FindingEvidence[];
  claimIds: string[];
  goalKeys: string[];
  confidence: "measured" | "for_information" | "general" | "none";
  limitations: string[];
  monitor: string;
  rank: number | null;
  factors: { name: string; points: number; detail: string }[];
};

export type Checkpoint = {
  id: string;
  title: string;
  whatToFilm: string;
  minimum: string;
  compareWith: string;
  whatCountsAsAChange: string;
  limitations: string[];
};

export type Reference = {
  sourceId: string;
  citation: string;
  url: string;
  kind: string;
  population: string;
};

export type Feedback = {
  feedbackVersion: string;
  evidenceVersion: string;
  goalsUsed: string[];
  items: FeedbackItem[];
  checkpoints: Checkpoint[];
  references: Reference[];
  recordingTips: string[];
  followups: FollowUp[]; // how this video answers the previous video's checkpoints
  explanationSource: "template" | "llm";
  summary: string;
};

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null =>
  v && typeof v === "object" ? (v as Obj) : null;
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strings = (v: unknown): string[] => list(v).map(str).filter(Boolean);
const categories: FeedbackCategory[] = [
  "observation",
  "focus",
  "priority",
  "education",
  "insufficient",
];

function parseEvidence(raw: unknown): FindingEvidence[] {
  const e = obj(raw);
  if (!e) return [];
  return [
    {
      metricKey: str(e.metric_key),
      label: str(e.label),
      value: num(e.value),
      unit: str(e.unit),
      low: num(e.low),
      high: num(e.high),
      cycles: num(e.n_cycles) ?? 0,
      status: str(e.status),
      samples: list(e.samples).flatMap((y): FindingSample[] => {
        const s = obj(y);
        const t = num(s?.t_s);
        const value = num(s?.value);
        return s && t !== null && value !== null
          ? [{ t, value, label: str(s.label) }]
          : [];
      }),
    },
  ];
}

function parseItem(raw: unknown): FeedbackItem[] {
  const f = obj(raw);
  const category = categories.find((c) => c === f?.category);
  if (!f || !category || !str(f.id) || !str(f.title) || !str(f.body)) return [];
  // General information is never personal, whatever the document says; and only a
  // priority carries a rank.
  const personal =
    category === "education" || category === "insufficient"
      ? false
      : f.personal === true;
  const explained = str(f.explained);
  return [
    {
      id: str(f.id),
      category,
      personal,
      title: str(f.title),
      text: explained || str(f.body),
      reworded: Boolean(explained),
      whyItMayMatter:
        category === "focus" || category === "priority"
          ? str(f.why_it_may_matter)
          : "",
      evidence:
        category === "education" ? [] : list(f.evidence).flatMap(parseEvidence),
      claimIds: strings(f.claim_ids),
      goalKeys: strings(f.goal_keys),
      confidence:
        (["measured", "for_information", "general", "none"] as const).find(
          (c) => c === f.confidence,
        ) ?? "none",
      limitations: strings(f.limitations),
      monitor: str(f.monitor),
      rank: category === "priority" ? num(f.rank) : null,
      factors:
        category === "priority"
          ? list(f.factors).flatMap((y) => {
              const x = obj(y);
              return x
                ? [
                    {
                      name: str(x.name),
                      points: num(x.points) ?? 0,
                      detail: str(x.detail),
                    },
                  ]
                : [];
            })
          : [],
    },
  ];
}

// Reads a feedback document. Returns null unless it is a version this page knows.
export function parseFeedback(raw: unknown): Feedback | null {
  const f = obj(raw);
  if (!f || !str(f.feedback_version).startsWith("1.")) return null;
  const items = list(f.items).flatMap(parseItem);
  const priorities = items
    .filter((i) => i.category === "priority" && i.rank !== null)
    .sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0))
    .slice(0, 3);
  const explanation = obj(f.explanation);
  return {
    feedbackVersion: str(f.feedback_version),
    evidenceVersion: str(f.evidence_version),
    goalsUsed: strings(f.goals_used),
    items: [...priorities, ...items.filter((i) => i.category !== "priority")],
    checkpoints: list(f.checkpoints).flatMap((y): Checkpoint[] => {
      const c = obj(y);
      return c && str(c.title)
        ? [
            {
              id: str(c.id),
              title: str(c.title),
              whatToFilm: str(c.what_to_film),
              minimum: str(c.minimum),
              compareWith: str(c.compare_with),
              whatCountsAsAChange: str(c.what_counts_as_a_change),
              limitations: strings(c.limitations),
            },
          ]
        : [];
    }),
    // Only links to doi.org are shown as links.
    references: list(f.references).flatMap((y): Reference[] => {
      const r = obj(y);
      const url = str(r?.url);
      return r && str(r.citation)
        ? [
            {
              sourceId: str(r.source_id),
              citation: str(r.citation),
              url: url.startsWith("https://doi.org/") ? url : "",
              kind: str(r.kind),
              population: str(r.population),
            },
          ]
        : [];
    }),
    recordingTips: strings(f.recording_tips),
    followups: parseFollowUps(f.followups),
    explanationSource: explanation?.source === "llm" ? "llm" : "template",
    summary: str(f.summary),
  };
}
