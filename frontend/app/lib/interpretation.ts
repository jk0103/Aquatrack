// Interpretation of one stored analysis, as the backend writes it
// (src/aquatrack/contracts.py, Interpretation). One document per run at
// videos/{videoId}/interpretations/{interpretationId}; earlier ones are never changed.
//
// Three levels are kept apart: observations (what was measured), issue candidates (what
// may need attention) and priorities (ranked, at most three, often none). Nothing here
// compares the swimmer with an ideal or with other swimmers. Pure parsing: no Firebase.

export type FindingSample = { t: number; value: number; label: string };

export type FindingEvidence = {
  metricKey: string;
  label: string;
  value: number | null;
  unit: string;
  low: number | null;
  high: number | null;
  cycles: number;
  status: string;
  samples: FindingSample[];
};

export type MetricChange = {
  metricKey: string;
  before: number;
  now: number;
  unit: string;
  threshold: number;
  changed: boolean;
};

export type Finding = {
  id: string;
  ruleId: string;
  level: "observation" | "issue_candidate";
  category: "timing" | "body_position" | "arm" | "history";
  title: string;
  description: string;
  metricKeys: string[];
  evidence: FindingEvidence[];
  evidenceClass: "measured" | "context_only";
  contextUsed: string[];
  changes: MetricChange[];
  limitations: string[];
  actionable: boolean;
  withheld: string[];
};

export type PriorityCandidate = {
  rank: number;
  findingId: string;
  title: string;
  score: number;
  factors: { name: string; points: number; detail: string }[];
};

export type Undetermined = {
  key: string;
  title: string;
  reason: string;
  kind: "measurement" | "interpretation";
};

export type RuleStatus = {
  ruleId: string;
  title: string;
  state: string;
  reason: string;
};

export type Interpretation = {
  interpretationVersion: string;
  rulesVersion: string;
  analysisId: string;
  baseline: boolean;
  context: { swimLevel: string | null; goals: string[]; notes: string[] };
  observations: Finding[];
  issueCandidates: Finding[];
  priorities: PriorityCandidate[];
  prioritiesNote: string;
  undetermined: Undetermined[];
  sessions: {
    videoId: string;
    compatible: boolean;
    reasons: string[];
    synthetic: boolean;
  }[];
  rules: RuleStatus[];
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
const categories = ["timing", "body_position", "arm", "history"] as const;

function parseFinding(raw: unknown, level: Finding["level"]): Finding[] {
  const f = obj(raw);
  const category = categories.find((c) => c === f?.category);
  // A finding stored at one level is never shown at another, whatever it says about itself.
  if (!f || !category || f.level !== level || !str(f.id) || !str(f.title))
    return [];
  return [
    {
      id: str(f.id),
      ruleId: str(f.rule_id),
      level,
      category,
      title: str(f.title),
      description: str(f.description),
      metricKeys: strings(f.metric_keys),
      evidence: list(f.evidence).flatMap((x): FindingEvidence[] => {
        const e = obj(x);
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
      }),
      evidenceClass:
        f.evidence_class === "measured" ? "measured" : "context_only",
      contextUsed: strings(f.context_used),
      changes: list(f.changes).flatMap((x): MetricChange[] => {
        const c = obj(x);
        const before = num(c?.before);
        const now = num(c?.now);
        return c && before !== null && now !== null
          ? [
              {
                metricKey: str(c.metric_key),
                before,
                now,
                unit: str(c.unit),
                threshold: num(c.threshold) ?? 0,
                changed: c.changed === true,
              },
            ]
          : [];
      }),
      limitations: strings(f.limitations),
      actionable: f.actionable === true,
      withheld: strings(f.withheld),
    },
  ];
}

// Reads an interpretation document. Returns null unless it is a version this page knows,
// so a newer or half-written document never shows up as findings.
export function parseInterpretation(raw: unknown): Interpretation | null {
  const i = obj(raw);
  if (!i || !str(i.interpretation_version).startsWith("1.")) return null;
  const issues = list(i.issue_candidates).flatMap((f) =>
    parseFinding(f, "issue_candidate"),
  );
  const known = new Set(issues.map((f) => f.id));
  const context = obj(i.context) ?? {};
  return {
    interpretationVersion: str(i.interpretation_version),
    rulesVersion: str(i.rules_version),
    analysisId: str(i.analysis_id),
    baseline: i.baseline !== false,
    context: {
      swimLevel: str(context.swim_level) || null,
      goals: strings(context.goals),
      notes: strings(context.notes),
    },
    observations: list(i.observations).flatMap((f) =>
      parseFinding(f, "observation"),
    ),
    issueCandidates: issues,
    // A priority must point at an issue candidate that is really there, and never more than three.
    priorities: list(i.priorities)
      .flatMap((x): PriorityCandidate[] => {
        const p = obj(x);
        const rank = num(p?.rank);
        if (!p || rank === null || !known.has(str(p.finding_id))) return [];
        return [
          {
            rank,
            findingId: str(p.finding_id),
            title: str(p.title),
            score: num(p.score) ?? 0,
            factors: list(p.factors).flatMap((y) => {
              const f = obj(y);
              return f
                ? [
                    {
                      name: str(f.name),
                      points: num(f.points) ?? 0,
                      detail: str(f.detail),
                    },
                  ]
                : [];
            }),
          },
        ];
      })
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 3),
    prioritiesNote: str(i.priorities_note),
    undetermined: list(i.undetermined).flatMap((x): Undetermined[] => {
      const u = obj(x);
      return u && str(u.title)
        ? [
            {
              key: str(u.key),
              title: str(u.title),
              reason: str(u.reason),
              kind:
                u.kind === "interpretation" ? "interpretation" : "measurement",
            },
          ]
        : [];
    }),
    sessions: list(i.sessions).flatMap((x) => {
      const s = obj(x);
      return s
        ? [
            {
              videoId: str(s.video_id),
              compatible: s.compatible === true,
              reasons: strings(s.reasons),
              synthetic: s.synthetic === true,
            },
          ]
        : [];
    }),
    rules: list(i.rules).flatMap((x) => {
      const r = obj(x);
      return r
        ? [
            {
              ruleId: str(r.rule_id),
              title: str(r.title),
              state: str(r.state),
              reason: str(r.reason),
            },
          ]
        : [];
    }),
    summary: str(i.summary),
  };
}
