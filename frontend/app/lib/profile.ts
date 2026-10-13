// The swimmer profile saved by the signup survey, one Firestore document per user at
// profiles/{uid}. firestore.rules checks the same ranges as checkDraft below.

import { doc, getDoc, serverTimestamp, setDoc } from "firebase/firestore";

import { db } from "@/app/lib/firebase";

export type SwimLevel = "beginner" | "hobby" | "masters" | "competitive";

export type Profile = {
  age: number;
  height_cm: number;
  weight_kg: number;
  swim_level: SwimLevel;
  sessions_per_week: number;
  minutes_per_day: number;
  // Optional: people without race times leave this empty.
  pbs: PersonalBest[];
};

export type PersonalBest = { event: string; pool: string; seconds: number };

export const PB_EVENTS = [
  "50 Free", "100 Free", "200 Free", "400 Free", "800 Free", "1500 Free",
  "50 Back", "100 Back", "200 Back",
  "50 Breast", "100 Breast", "200 Breast",
  "50 Fly", "100 Fly", "200 Fly",
  "100 IM", "200 IM", "400 IM",
];
export const PB_POOLS = ["25 m", "50 m", "25 yd"];
export const MAX_PBS = 20; // keep in sync with firestore.rules

// "1:01.30" or "28.1" to seconds; null if it isn't a time.
export function parseSwimTime(text: string): number | null {
  const m = text.trim().match(/^(?:(\d{1,2}):)?(\d{1,2}(?:\.\d{1,2})?)$/);
  if (!m) return null;
  const minutes = m[1] ? Number(m[1]) : 0;
  const seconds = Number(m[2]);
  if (m[1] && seconds >= 60) return null;
  return Math.round((minutes * 60 + seconds) * 100) / 100;
}

export function formatSwimTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(2);
  return m ? `${m}:${s.padStart(5, "0")}` : s;
}

export const SWIM_LEVELS: { value: SwimLevel; label: string; note: string }[] = [
  { value: "beginner", label: "Beginner", note: "Still learning the strokes" },
  { value: "hobby", label: "Hobby", note: "Swim for fun or fitness" },
  { value: "masters", label: "Masters", note: "Adult club or masters team" },
  { value: "competitive", label: "Competitive", note: "Train and race in meets" },
];

export function levelLabel(level: SwimLevel): string {
  return SWIM_LEVELS.find((l) => l.value === level)?.label ?? level;
}

// Form state: inputs hold strings until the answers are checked.
type NumberKey = Exclude<keyof Profile, "pbs">;
export type PbDraft = { event: string; pool: string; time: string };
export type ProfileDraft = { [K in NumberKey]: string } & { pbs: PbDraft[] };

export const emptyDraft: ProfileDraft = {
  age: "",
  height_cm: "",
  weight_kg: "",
  swim_level: "",
  sessions_per_week: "",
  minutes_per_day: "",
  pbs: [],
};

export function toDraft(p: Profile): ProfileDraft {
  return {
    age: String(p.age),
    height_cm: String(p.height_cm),
    weight_kg: String(p.weight_kg),
    swim_level: p.swim_level,
    sessions_per_week: String(p.sessions_per_week),
    minutes_per_day: String(p.minutes_per_day),
    pbs: p.pbs.map((pb) => ({ event: pb.event, pool: pb.pool, time: formatSwimTime(pb.seconds) })),
  };
}

type Check = { key: NumberKey; label: string; min: number; max: number; integer?: boolean };

export const BODY_CHECKS: Check[] = [
  { key: "age", label: "Age", min: 5, max: 100, integer: true },
  { key: "height_cm", label: "Height", min: 80, max: 250 },
  { key: "weight_kg", label: "Weight", min: 15, max: 250 },
];

export const TRAINING_CHECKS: Check[] = [
  { key: "sessions_per_week", label: "Sessions per week", min: 0, max: 14, integer: true },
  { key: "minutes_per_day", label: "Time per day", min: 0, max: 600, integer: true },
];

// Returns an error message for the first answer that's missing or out of range.
export function checkDraft(draft: ProfileDraft, checks: Check[]): string | null {
  for (const { key, label, min, max, integer } of checks) {
    const raw = draft[key].trim();
    const n = Number(raw);
    if (!raw || Number.isNaN(n)) return `Enter your ${label.toLowerCase()}.`;
    if (integer && !Number.isInteger(n)) return `${label} must be a whole number.`;
    if (n < min || n > max) return `${label} must be between ${min} and ${max}.`;
  }
  return null;
}

// Personal bests are optional: fully blank rows are ignored.
export function checkPbs(draft: ProfileDraft): string | null {
  const seen = new Set<string>();
  for (const pb of draft.pbs) {
    if (!pb.time.trim()) continue;
    if (!pb.event) return "Choose the event for each time you enter.";
    const seconds = parseSwimTime(pb.time);
    if (seconds === null) return `Enter times like 28.45 or 1:02.30 (${pb.event}).`;
    if (seconds < 10 || seconds > 3600) return `That time for ${pb.event} looks off.`;
    const key = `${pb.event}|${pb.pool}`;
    if (seen.has(key)) return `${pb.event} (${pb.pool}) is listed twice.`;
    seen.add(key);
  }
  if (seen.size > MAX_PBS) return `You can add up to ${MAX_PBS} times.`;
  return null;
}

export function checkLevel(draft: ProfileDraft): string | null {
  return draft.swim_level ? null : "Choose the option that fits your swimming best.";
}

export function fromDraft(draft: ProfileDraft): Profile {
  return {
    age: Number(draft.age),
    height_cm: Number(draft.height_cm),
    weight_kg: Number(draft.weight_kg),
    swim_level: draft.swim_level as SwimLevel,
    sessions_per_week: Number(draft.sessions_per_week),
    minutes_per_day: Number(draft.minutes_per_day),
    pbs: draft.pbs
      .filter((pb) => pb.event && pb.time.trim())
      .map((pb) => ({ event: pb.event, pool: pb.pool, seconds: parseSwimTime(pb.time)! })),
  };
}

export function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

// The saved profile, or null if the survey hasn't been filled in.
export async function loadProfile(uid: string): Promise<Profile | null> {
  const snap = await getDoc(doc(db, "profiles", uid));
  if (!snap.exists()) return null;
  const d = snap.data();
  return {
    age: d.age,
    height_cm: d.height_cm,
    weight_kg: d.weight_kg,
    swim_level: d.swim_level,
    sessions_per_week: d.sessions_per_week,
    minutes_per_day: d.minutes_per_day,
    pbs: Array.isArray(d.pbs) ? d.pbs : [],
  };
}

export async function saveProfile(uid: string, profile: Profile): Promise<void> {
  await setDoc(doc(db, "profiles", uid), { ...profile, updatedAt: serverTimestamp() });
}
