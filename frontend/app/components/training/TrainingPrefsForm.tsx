"use client";

import { useState } from "react";

import { Button } from "@/app/components/ui";
import { saveProfile, type Profile } from "@/app/lib/profile";
import {
  DAY_OPTIONS,
  DIFFICULTY_OPTIONS,
  EQUIPMENT_OPTIONS,
  STROKE_OPTIONS,
  TIME_OPTIONS,
} from "@/app/lib/training";

const input =
  "mt-1 block w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-sky-600 focus:ring-4 focus:ring-sky-600/15 focus:outline-none";

function Checks({
  legend,
  options,
  value,
  onChange,
}: {
  legend: string;
  options: { value: string; label: string }[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <fieldset>
      <legend className="text-sm font-medium text-slate-700">{legend}</legend>
      <div className="mt-1.5 flex flex-wrap gap-2">
        {options.map((o) => {
          const on = value.includes(o.value);
          return (
            <label
              key={o.value}
              className={`cursor-pointer rounded-full border px-3 py-1.5 text-sm font-medium ${
                on
                  ? "border-sky-700 bg-sky-700 text-white"
                  : "border-slate-300 bg-surface text-slate-700 hover:bg-slate-50"
              }`}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={on}
                onChange={() =>
                  onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])
                }
              />
              {o.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

// Training preferences live on the swimmer's own profile. How often and how long they swim
// are the profile's existing answers, edited here too so they are never asked twice.
export function TrainingPrefsForm({
  uid,
  profile,
  onSaved,
  onCancel,
}: {
  uid: string;
  profile: Profile;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [prefs, setPrefs] = useState(profile.training);
  const [sessions, setSessions] = useState(String(profile.sessions_per_week));
  const [minutes, setMinutes] = useState(String(profile.minutes_per_day));
  const [distance, setDistance] = useState(
    prefs.typical_distance_m ? String(prefs.typical_distance_m) : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(sessions);
    const m = Number(minutes);
    const d = distance.trim() ? Number(distance) : null;
    if (!Number.isInteger(n) || n < 0 || n > 14)
      return setError("Sessions per week must be a whole number between 0 and 14.");
    if (!Number.isInteger(m) || m < 0 || m > 600)
      return setError("Time per session must be between 0 and 600 minutes.");
    if (d !== null && (!Number.isFinite(d) || d < 100 || d > 10000))
      return setError("Typical distance must be between 100 and 10,000 m, or left empty.");
    if (prefs.days.length && n > prefs.days.length)
      return setError(
        `You chose ${prefs.days.length} available ${prefs.days.length === 1 ? "day" : "days"} but ${n} sessions per week. Add days or lower the sessions.`,
      );
    setBusy(true);
    setError(null);
    try {
      await saveProfile(uid, {
        ...profile,
        sessions_per_week: n,
        minutes_per_day: m,
        training: { ...prefs, typical_distance_m: d === null ? null : Math.round(d) },
      });
      onSaved();
    } catch {
      setError("Your preferences could not be saved. Try again.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Checks
        legend="Days you can swim"
        options={DAY_OPTIONS}
        value={prefs.days}
        onChange={(days) => setPrefs({ ...prefs, days })}
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block text-sm font-medium text-slate-700">
          Sessions per week
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={14}
            className={input}
            value={sessions}
            onChange={(e) => setSessions(e.target.value)}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Time per session (min)
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={600}
            className={input}
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Preferred time
          <select
            className={input}
            value={prefs.time_of_day}
            onChange={(e) => setPrefs({ ...prefs, time_of_day: e.target.value })}
          >
            {TIME_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Preferred difficulty
          <select
            className={input}
            value={prefs.difficulty}
            onChange={(e) => setPrefs({ ...prefs, difficulty: e.target.value })}
          >
            {DIFFICULTY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block max-w-xs text-sm font-medium text-slate-700">
        Typical distance per session (m){" "}
        <span className="font-normal text-slate-500">(optional)</span>
        <input
          type="number"
          inputMode="numeric"
          min={100}
          max={10000}
          step={50}
          className={input}
          value={distance}
          onChange={(e) => setDistance(e.target.value)}
        />
      </label>
      <Checks
        legend="Strokes you like to swim"
        options={STROKE_OPTIONS.map((s) => ({ value: s, label: s }))}
        value={prefs.strokes}
        onChange={(strokes) => setPrefs({ ...prefs, strokes })}
      />
      <Checks
        legend="Equipment you have"
        options={EQUIPMENT_OPTIONS}
        value={prefs.equipment}
        onChange={(equipment) => setPrefs({ ...prefs, equipment })}
      />
      <p className="text-xs text-slate-500">
        Your swimming level and goals are part of your profile. No health or medical
        information is asked for or used.
      </p>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save preferences"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
