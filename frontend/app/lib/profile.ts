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
};

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
export type ProfileDraft = { [K in keyof Profile]: string };

export const emptyDraft: ProfileDraft = {
  age: "",
  height_cm: "",
  weight_kg: "",
  swim_level: "",
  sessions_per_week: "",
  minutes_per_day: "",
};

export function toDraft(p: Profile): ProfileDraft {
  return {
    age: String(p.age),
    height_cm: String(p.height_cm),
    weight_kg: String(p.weight_kg),
    swim_level: p.swim_level,
    sessions_per_week: String(p.sessions_per_week),
    minutes_per_day: String(p.minutes_per_day),
  };
}

type Check = { key: keyof Profile; label: string; min: number; max: number; integer?: boolean };

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
  };
}

export async function saveProfile(uid: string, profile: Profile): Promise<void> {
  await setDoc(doc(db, "profiles", uid), { ...profile, updatedAt: serverTimestamp() });
}
