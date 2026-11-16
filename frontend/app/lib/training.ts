// Training plans, sessions and the calendar as the backend returns them
// (src/aquatrack/api/training.py, contracts in src/aquatrack/training/models.py), plus the
// pure helpers the pages use: local dates, the month grid, and editing a session's
// activity list. Pure code: no Firebase, no fetch.
//
// Dates are the swimmer's local calendar dates ("YYYY-MM-DD"). They are never turned into
// a Date in UTC and back, which is how a session ends up on the wrong day.

export type Basis = "analysis_based" | "goal_based" | "general";
export type ItemSource = "recommended" | "modified" | "manual";
export type SessionStatus =
  | "planned"
  | "completed"
  | "skipped"
  | "canceled"
  | "replaced";
export type EvidenceClass =
  | "research_supported"
  | "coaching_guidance"
  | "general_suggestion"
  | "unverified";

export type PlanItem = {
  activity_id: string; // "" for an activity the swimmer typed in
  name: string;
  category: string;
  minutes: number;
  distance_m: number | null;
  sets: string;
  intensity: string;
  rest: string;
  instructions: string[];
  equipment: string[];
  safety: string[];
  source: ItemSource;
  recommendation_id: string;
  basis: Basis | null;
  evidence_class: EvidenceClass | null;
  done: boolean;
};

export type SessionCheckpoint = {
  title: string;
  what_to_film: string;
  checkpoint_ids: string[];
  source_video_id: string;
  note: string;
};

export type TrainingSession = {
  id: string;
  plan_id: string;
  plan_version: number;
  date: string;
  time: string;
  title: string;
  objective: string;
  level: string;
  minutes: number;
  distance_m: number | null;
  intensity: string;
  focus: string;
  basis: Basis | null;
  items: PlanItem[];
  goal_keys: string[];
  finding_ids: string[];
  checkpoint: SessionCheckpoint | null;
  rest_guidance: string;
  safety: string[];
  status: SessionStatus;
  origin: "generated" | "manual";
  edited: boolean;
  completion: { completed_on: string; note: string } | null;
  linked_video_id: string;
  linked_video_removed: boolean;
  explained: string;
};

export type Recommendation = {
  id: string;
  basis: Basis;
  activity_id: string;
  activity_name: string;
  reason: string;
  inputs_used: string[];
  goal_keys: string[];
  finding_ids: string[];
  finding_titles: string[];
  video_id: string;
  evidence_class: EvidenceClass;
  source_ids: string[];
  watch_for: string;
  video_can_measure: string;
  assumptions: string[];
  limitations: string[];
};

export type TrainingPlan = {
  id: string;
  version: number;
  kind: "session" | "week";
  basis: Basis;
  title: string;
  summary: string;
  explained: string;
  explanation: { source: "template" | "llm"; model: string; note: string };
  start_date: string;
  end_date: string;
  status: "preview" | "active" | "replaced";
  sessions: TrainingSession[];
  rest_days: { date: string; guidance: string }[];
  recommendations: Recommendation[];
  inputs: { video_id: string; analysis_state: string; analysis_removed: boolean };
  assumptions: string[];
  limitations: string[];
  notes: string[];
};

export type Activity = {
  id: string;
  name: string;
  category: string;
  purpose: string;
  instructions: string[];
  min_minutes: number;
  max_minutes: number;
  intensity: string;
  rest: string;
  equipment: string[];
  goals: string[];
  watch_for: string;
  video_can_measure: string;
  safety: string[];
  evidence_class: EvidenceClass;
  source_ids: string[];
  limitations: string[];
  not_offered: string | null; // why the swimmer cannot add it, or null
};

export type TrainingSource = {
  id: string;
  kind: "review" | "original_study" | "coaching_page";
  title: string;
  authors: string[];
  year: number | null;
  publisher: string;
  url: string;
  read: "abstract" | "page";
  says: string;
  limits: string;
};

export type Swimmer = {
  level: string | null;
  sessions_per_week: number | null;
  session_minutes: number | null;
  days: string[];
  time_of_day: string;
  typical_distance_m: number | null;
  strokes: string[];
  equipment: string[];
  difficulty: string;
  goals: string[];
  primary_goal: string | null;
  missing: string[];
};

export type WeekCounts = {
  start: string;
  end: string;
  planned: number;
  completed: number;
  skipped: number;
  canceled: number;
};

export type TrainingOverview = {
  swimmer: Swimmer;
  analysis: {
    state: "none" | "unavailable" | "no_supported_issue" | "supported";
    video_id: string;
    findings: { id: string; title: string }[];
    checkpoints: { id: string; title: string; what_to_film: string }[];
  };
  recommendations: Recommendation[];
  library: Activity[];
  sources: TrainingSource[];
  plans: TrainingPlan[];
  week: WeekCounts;
  upcoming: TrainingSession[];
  history: TrainingSession[];
  totals: { completed: number; skipped: number };
  llm_enabled: boolean;
};

export type CalendarFeed = {
  sessions: TrainingSession[];
  rest_days: { date: string; guidance: string; plan_id: string }[];
  videos: { id: string; file_name: string; recorded_at: string }[];
};

export type SaveResult =
  | { saved: true; plan: TrainingPlan }
  | {
      saved: false;
      conflict: {
        kind: "week_overlap" | "date_has_session";
        plans: {
          id: string;
          title: string;
          version: number;
          edited: number;
          unedited: number;
          recorded: number;
        }[];
        sessions: { id: string; title: string; date: string }[];
      };
    };

// ---- reading what the backend sent. Anything missing gets a safe empty value; a value of
// the wrong kind is dropped rather than shown.

type Raw = Record<string, unknown>;
const obj = (v: unknown): Raw => (v && typeof v === "object" ? (v as Raw) : {});
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown): number =>
  typeof v === "number" && Number.isFinite(v) ? v : 0;
const numOrNull = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strings = (v: unknown): string[] =>
  list(v).filter((x): x is string => typeof x === "string");
const oneOf = <T extends string>(v: unknown, options: T[], fallback: T): T =>
  options.includes(v as T) ? (v as T) : fallback;

const BASES: Basis[] = ["analysis_based", "goal_based", "general"];
const CLASSES: EvidenceClass[] = [
  "research_supported",
  "coaching_guidance",
  "general_suggestion",
  "unverified",
];

export function parseItem(raw: unknown): PlanItem {
  const r = obj(raw);
  return {
    activity_id: str(r.activity_id),
    name: str(r.name),
    category: str(r.category),
    minutes: num(r.minutes),
    distance_m: numOrNull(r.distance_m),
    sets: str(r.sets),
    intensity: str(r.intensity),
    rest: str(r.rest),
    instructions: strings(r.instructions),
    equipment: strings(r.equipment),
    safety: strings(r.safety),
    source: oneOf(r.source, ["recommended", "modified", "manual"], "manual"),
    recommendation_id: str(r.recommendation_id),
    basis: BASES.includes(r.basis as Basis) ? (r.basis as Basis) : null,
    evidence_class: CLASSES.includes(r.evidence_class as EvidenceClass)
      ? (r.evidence_class as EvidenceClass)
      : null,
    done: r.done === true,
  };
}

export function parseSession(raw: unknown): TrainingSession {
  const r = obj(raw);
  const cp = r.checkpoint ? obj(r.checkpoint) : null;
  const done = r.completion ? obj(r.completion) : null;
  return {
    id: str(r.id),
    plan_id: str(r.plan_id),
    plan_version: num(r.plan_version),
    date: isIsoDate(str(r.date)) ? str(r.date) : "",
    time: str(r.time),
    title: str(r.title),
    objective: str(r.objective),
    level: str(r.level),
    minutes: num(r.minutes),
    distance_m: numOrNull(r.distance_m),
    intensity: str(r.intensity),
    focus: str(r.focus),
    basis: BASES.includes(r.basis as Basis) ? (r.basis as Basis) : null,
    items: list(r.items).map(parseItem),
    goal_keys: strings(r.goal_keys),
    finding_ids: strings(r.finding_ids),
    checkpoint: cp
      ? {
          title: str(cp.title),
          what_to_film: str(cp.what_to_film),
          checkpoint_ids: strings(cp.checkpoint_ids),
          source_video_id: str(cp.source_video_id),
          note: str(cp.note),
        }
      : null,
    rest_guidance: str(r.rest_guidance),
    safety: strings(r.safety),
    status: oneOf(
      r.status,
      ["planned", "completed", "skipped", "canceled", "replaced"],
      "planned",
    ),
    origin: oneOf(r.origin, ["generated", "manual"], "manual"),
    edited: r.edited === true,
    completion: done
      ? { completed_on: str(done.completed_on), note: str(done.note) }
      : null,
    linked_video_id: str(r.linked_video_id),
    linked_video_removed: r.linked_video_removed === true,
    explained: str(r.explained),
  };
}

function parseRecommendation(raw: unknown): Recommendation {
  const r = obj(raw);
  return {
    id: str(r.id),
    basis: oneOf(r.basis, BASES, "general"),
    activity_id: str(r.activity_id),
    activity_name: str(r.activity_name),
    reason: str(r.reason),
    inputs_used: strings(r.inputs_used),
    goal_keys: strings(r.goal_keys),
    finding_ids: strings(r.finding_ids),
    finding_titles: strings(r.finding_titles),
    video_id: str(r.video_id),
    evidence_class: oneOf(r.evidence_class, CLASSES, "general_suggestion"),
    source_ids: strings(r.source_ids),
    watch_for: str(r.watch_for),
    video_can_measure: str(r.video_can_measure),
    assumptions: strings(r.assumptions),
    limitations: strings(r.limitations),
  };
}

export function parsePlan(raw: unknown): TrainingPlan | null {
  const r = obj(raw);
  if (!isIsoDate(str(r.start_date)) || !str(r.title)) return null;
  const e = obj(r.explanation);
  const inputs = obj(r.inputs);
  return {
    id: str(r.id),
    version: num(r.version) || 1,
    kind: oneOf(r.kind, ["session", "week"], "week"),
    basis: oneOf(r.basis, BASES, "general"),
    title: str(r.title),
    summary: str(r.summary),
    explained: str(r.explained),
    explanation: {
      source: oneOf(e.source, ["template", "llm"], "template"),
      model: str(e.model),
      note: str(e.note),
    },
    start_date: str(r.start_date),
    end_date: str(r.end_date),
    status: oneOf(r.status, ["preview", "active", "replaced"], "preview"),
    sessions: list(r.sessions)
      .map(parseSession)
      .filter((s) => s.date),
    rest_days: list(r.rest_days)
      .map((d) => ({ date: str(obj(d).date), guidance: str(obj(d).guidance) }))
      .filter((d) => isIsoDate(d.date)),
    recommendations: list(r.recommendations).map(parseRecommendation),
    inputs: {
      video_id: str(inputs.video_id),
      analysis_state: str(inputs.analysis_state),
      analysis_removed: inputs.analysis_removed === true,
    },
    assumptions: strings(r.assumptions),
    limitations: strings(r.limitations),
    notes: strings(r.notes),
  };
}

function parseActivity(raw: unknown): Activity {
  const r = obj(raw);
  return {
    id: str(r.id),
    name: str(r.name),
    category: str(r.category),
    purpose: str(r.purpose),
    instructions: strings(r.instructions),
    min_minutes: num(r.min_minutes),
    max_minutes: num(r.max_minutes),
    intensity: str(r.intensity),
    rest: str(r.rest),
    equipment: strings(r.equipment),
    goals: strings(r.goals),
    watch_for: str(r.watch_for),
    video_can_measure: str(r.video_can_measure),
    safety: strings(r.safety),
    evidence_class: oneOf(r.evidence_class, CLASSES, "general_suggestion"),
    source_ids: strings(r.source_ids),
    limitations: strings(r.limitations),
    not_offered: typeof r.not_offered === "string" ? r.not_offered : null,
  };
}

function parseWeek(raw: unknown): WeekCounts {
  const r = obj(raw);
  return {
    start: str(r.start),
    end: str(r.end),
    planned: num(r.planned),
    completed: num(r.completed),
    skipped: num(r.skipped),
    canceled: num(r.canceled),
  };
}

export function parseOverview(raw: unknown): TrainingOverview | null {
  const r = obj(raw);
  if (!r.swimmer || !r.week) return null;
  const s = obj(r.swimmer);
  const a = obj(r.analysis);
  return {
    swimmer: {
      level: typeof s.level === "string" ? s.level : null,
      sessions_per_week: numOrNull(s.sessions_per_week),
      session_minutes: numOrNull(s.session_minutes),
      days: strings(s.days),
      time_of_day: str(s.time_of_day),
      typical_distance_m: numOrNull(s.typical_distance_m),
      strokes: strings(s.strokes),
      equipment: strings(s.equipment),
      difficulty: str(s.difficulty),
      goals: strings(s.goals),
      primary_goal: typeof s.primary_goal === "string" ? s.primary_goal : null,
      missing: strings(s.missing),
    },
    analysis: {
      state: oneOf(
        a.state,
        ["none", "unavailable", "no_supported_issue", "supported"],
        "none",
      ),
      video_id: str(a.video_id),
      findings: list(a.findings).map((f) => ({
        id: str(obj(f).id),
        title: str(obj(f).title),
      })),
      checkpoints: list(a.checkpoints).map((c) => ({
        id: str(obj(c).id),
        title: str(obj(c).title),
        what_to_film: str(obj(c).what_to_film),
      })),
    },
    recommendations: list(r.recommendations).map(parseRecommendation),
    library: list(r.library)
      .map(parseActivity)
      .filter((x) => x.id),
    sources: list(r.sources).map((x) => {
      const o = obj(x);
      return {
        id: str(o.id),
        kind: oneOf(
          o.kind,
          ["review", "original_study", "coaching_page"],
          "coaching_page",
        ),
        title: str(o.title),
        authors: strings(o.authors),
        year: numOrNull(o.year),
        publisher: str(o.publisher),
        url: str(o.url).startsWith("https://") ? str(o.url) : "",
        read: oneOf(o.read, ["abstract", "page"], "page"),
        says: str(o.says),
        limits: str(o.limits),
      };
    }),
    plans: list(r.plans)
      .map(parsePlan)
      .filter((p): p is TrainingPlan => p !== null),
    week: parseWeek(r.week),
    upcoming: list(r.upcoming)
      .map(parseSession)
      .filter((x) => x.date),
    history: list(r.history)
      .map(parseSession)
      .filter((x) => x.date),
    totals: {
      completed: num(obj(r.totals).completed),
      skipped: num(obj(r.totals).skipped),
    },
    llm_enabled: r.llm_enabled === true,
  };
}

export function parseCalendar(raw: unknown): CalendarFeed {
  const r = obj(raw);
  return {
    sessions: list(r.sessions)
      .map(parseSession)
      .filter((s) => s.date),
    rest_days: list(r.rest_days)
      .map((d) => ({
        date: str(obj(d).date),
        guidance: str(obj(d).guidance),
        plan_id: str(obj(d).plan_id),
      }))
      .filter((d) => isIsoDate(d.date)),
    videos: list(r.videos).map((v) => ({
      id: str(obj(v).id),
      file_name: str(obj(v).file_name),
      recorded_at: str(obj(v).recorded_at),
    })),
  };
}

export function parseSaveResult(raw: unknown): SaveResult | null {
  const r = obj(raw);
  if (r.saved === true) {
    const plan = parsePlan(r.plan);
    return plan ? { saved: true, plan } : null;
  }
  const c = obj(r.conflict);
  if (r.saved !== false || !c.kind) return null;
  return {
    saved: false,
    conflict: {
      kind: oneOf(c.kind, ["week_overlap", "date_has_session"], "week_overlap"),
      plans: list(c.plans).map((p) => ({
        id: str(obj(p).id),
        title: str(obj(p).title),
        version: num(obj(p).version),
        edited: num(obj(p).edited),
        unedited: num(obj(p).unedited),
        recorded: num(obj(p).recorded),
      })),
      sessions: list(c.sessions).map((s) => ({
        id: str(obj(s).id),
        title: str(obj(s).title),
        date: str(obj(s).date),
      })),
    },
  };
}

// ---- labels. The same words everywhere, and nothing that claims more than it should.

export function basisLabel(basis: Basis | null): string {
  if (basis === "analysis_based") return "Analysis-based";
  if (basis === "goal_based") return "Goal-based";
  if (basis === "general") return "General";
  return "Created by you";
}

export function basisNote(basis: Basis | null): string {
  if (basis === "analysis_based")
    return "Linked to a supported finding in your own analysis. Something to look at, not a confirmed fault.";
  if (basis === "goal_based")
    return "Chosen from your goals. It does not mean a problem was found in your swimming.";
  if (basis === "general")
    return "A conservative general suggestion. Add goals for a plan built around them.";
  return "You wrote this session yourself.";
}

export function basisTone(basis: Basis | null): "teal" | "sky" | "slate" {
  return basis === "analysis_based"
    ? "teal"
    : basis === "goal_based"
      ? "sky"
      : "slate";
}

export function sourceLabel(source: ItemSource): string {
  return source === "recommended"
    ? "Recommended"
    : source === "modified"
      ? "Changed by you"
      : "Added by you";
}

export function evidenceLabel(c: EvidenceClass | null): string {
  if (c === "research_supported") return "Research-supported practice";
  if (c === "coaching_guidance") return "Coaching guidance";
  if (c === "general_suggestion") return "General suggestion";
  return "";
}

export function statusLabel(status: SessionStatus): string {
  return {
    planned: "Planned",
    completed: "Completed",
    skipped: "Skipped",
    canceled: "Cancelled",
    replaced: "Replaced",
  }[status];
}

export function statusTone(
  status: SessionStatus,
): "sky" | "teal" | "amber" | "slate" {
  return status === "completed"
    ? "teal"
    : status === "planned"
      ? "sky"
      : status === "skipped"
        ? "amber"
        : "slate";
}

export const DAY_OPTIONS = [
  { value: "mon", label: "Mon" },
  { value: "tue", label: "Tue" },
  { value: "wed", label: "Wed" },
  { value: "thu", label: "Thu" },
  { value: "fri", label: "Fri" },
  { value: "sat", label: "Sat" },
  { value: "sun", label: "Sun" },
];
export const EQUIPMENT_OPTIONS = [
  { value: "kickboard", label: "Kickboard" },
  { value: "pull_buoy", label: "Pull buoy" },
  { value: "fins", label: "Fins" },
  { value: "snorkel", label: "Snorkel" },
];
export const TIME_OPTIONS = [
  { value: "", label: "No preference" },
  { value: "morning", label: "Morning" },
  { value: "midday", label: "Midday" },
  { value: "evening", label: "Evening" },
];
export const DIFFICULTY_OPTIONS = [
  { value: "", label: "Not set" },
  { value: "easy", label: "Easy" },
  { value: "moderate", label: "Moderate" },
  { value: "challenging", label: "Challenging" },
];
export const STROKE_OPTIONS = [
  "Freestyle",
  "Backstroke",
  "Breaststroke",
  "Butterfly",
];

// ---- local calendar dates

export function isIsoDate(text: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
  const [y, m, d] = text.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return (
    date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d
  );
}

// The date on the swimmer's own clock. Never toISOString(), which answers in UTC and is
// a day off for part of every day away from Greenwich.
export function localIso(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function fromIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d, 12); // midday: a clock change can never move the day
}

export function addDays(iso: string, days: number): string {
  const date = fromIso(iso);
  date.setDate(date.getDate() + days);
  return localIso(date);
}

// Monday of the week the date is in.
export function weekStart(iso: string): string {
  const weekday = (fromIso(iso).getDay() + 6) % 7; // Monday = 0
  return addDays(iso, -weekday);
}

export function weekDates(iso: string): string[] {
  const start = weekStart(iso);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

// The weeks shown for a month: whole Monday-to-Sunday rows covering it.
export function monthGrid(year: number, month: number): string[][] {
  const first = localIso(new Date(year, month, 1, 12));
  const last = localIso(new Date(year, month + 1, 0, 12));
  const rows: string[][] = [];
  for (let day = weekStart(first); day <= last; day = addDays(day, 7))
    rows.push(weekDates(day));
  return rows;
}

export function formatDay(
  iso: string,
  opts: Intl.DateTimeFormatOptions = {
    weekday: "short",
    month: "short",
    day: "numeric",
  },
): string {
  return isIsoDate(iso) ? fromIso(iso).toLocaleDateString("en-US", opts) : iso;
}

export function monthTitle(year: number, month: number): string {
  return new Date(year, month, 1, 12).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

export function byDate<T extends { date: string }>(
  entries: T[],
): Map<string, T[]> {
  const out = new Map<string, T[]>();
  for (const e of entries) out.set(e.date, [...(out.get(e.date) ?? []), e]);
  return out;
}

// ---- editing a session's activity list. Pure, so the same rules can be tested without a
// browser. The backend checks everything again; this only gives an early, clear message.

export type DraftItem = { activity_id: string; name: string; minutes: number };

export function toDraftItems(items: PlanItem[]): DraftItem[] {
  return items.map((i) => ({
    activity_id: i.activity_id,
    name: i.name,
    minutes: i.minutes,
  }));
}

export function setMinutes(
  items: DraftItem[],
  index: number,
  minutes: number,
): DraftItem[] {
  return items.map((item, i) => (i === index ? { ...item, minutes } : item));
}

export function removeItem(items: DraftItem[], index: number): DraftItem[] {
  return items.filter((_, i) => i !== index);
}

export function addActivity(
  items: DraftItem[],
  activity: Activity,
): DraftItem[] {
  if (items.some((i) => i.activity_id === activity.id)) return items;
  return [
    ...items,
    {
      activity_id: activity.id,
      name: activity.name,
      minutes: activity.min_minutes,
    },
  ];
}

export function addCustom(items: DraftItem[], name: string): DraftItem[] {
  const clean = name.trim();
  return clean
    ? [...items, { activity_id: "", name: clean, minutes: 10 }]
    : items;
}

export const MAX_SESSION_MINUTES = 180;

export function draftMinutes(items: DraftItem[]): number {
  return items.reduce((sum, i) => sum + (Number.isFinite(i.minutes) ? i.minutes : 0), 0);
}

// The first thing wrong with a draft, or null. Mirrors the backend's messages.
export function checkDraftSession(
  draft: { date: string; time: string; title: string; items: DraftItem[] },
  library: Activity[],
): string | null {
  if (!isIsoDate(draft.date)) return "Choose a date for the session.";
  if (draft.time && !/^([01]\d|2[0-3]):[0-5]\d$/.test(draft.time))
    return "Enter the time as HH:MM, or leave it empty.";
  const title = draft.title.trim();
  if (!title || title.length > 80)
    return "Give the session a title of up to 80 characters.";
  if (!draft.items.length) return "A session needs at least one activity.";
  for (const item of draft.items) {
    if (!Number.isInteger(item.minutes))
      return `${item.name}: give a whole number of minutes.`;
    const known = library.find((a) => a.id === item.activity_id);
    if (item.activity_id && !known)
      return `${item.name} is not in the activity library.`;
    const [lo, hi] = known ? [known.min_minutes, known.max_minutes] : [1, 120];
    if (item.minutes < lo || item.minutes > hi)
      return `${item.name}: choose between ${lo} and ${hi} minutes.`;
  }
  const total = draftMinutes(draft.items);
  if (total > MAX_SESSION_MINUTES)
    return `That adds up to ${total} minutes; keep a session under ${MAX_SESSION_MINUTES}.`;
  return null;
}

export function sessionMeta(s: {
  minutes: number;
  distance_m: number | null;
  intensity: string;
}): string {
  return [
    `${s.minutes} min`,
    s.distance_m ? `about ${s.distance_m.toLocaleString("en-US")} m` : "",
    s.intensity,
  ]
    .filter(Boolean)
    .join(" · ");
}
