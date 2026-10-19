"use client";

import type { ReactNode } from "react";

import { MAX_PBS, PB_EVENTS, PB_POOLS, SWIM_LEVELS, type PbDraft, type ProfileDraft } from "@/app/lib/profile";

// Profile questions, shared by the signup survey and the edit profile page.

type FieldsProps = {
  draft: ProfileDraft;
  set: (changes: Partial<ProfileDraft>) => void;
};

const inputClass =
  "block w-full rounded-lg border border-slate-300 bg-surface px-3.5 py-2.5 text-slate-900 shadow-sm " +
  "placeholder:text-slate-400 focus:border-sky-600 focus:outline-none focus:ring-4 focus:ring-sky-600/15";

function NumberField({
  label,
  unit,
  value,
  onChange,
  placeholder,
  step = "1",
}: {
  label: string;
  unit: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  step?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-medium text-slate-700">{label}</span>
      <span className="relative block">
        <input
          type="number"
          inputMode="decimal"
          step={step}
          min="0"
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className={`${inputClass} pr-14`}
        />
        <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3.5 text-sm text-slate-500">
          {unit}
        </span>
      </span>
    </label>
  );
}

function Chip({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
        on
          ? "bg-sky-700 text-white shadow-sm"
          : "border border-slate-300 bg-surface text-slate-700 hover:border-sky-400"
      }`}
    >
      {children}
    </button>
  );
}

export function BodyFields({ draft, set }: FieldsProps) {
  return (
    <div className="grid gap-5 sm:grid-cols-3">
      <NumberField
        label="Age"
        unit="years"
        placeholder="21"
        value={draft.age}
        onChange={(age) => set({ age })}
      />
      <NumberField
        label="Height"
        unit="cm"
        placeholder="175"
        step="0.1"
        value={draft.height_cm}
        onChange={(height_cm) => set({ height_cm })}
      />
      <NumberField
        label="Weight"
        unit="kg"
        placeholder="70"
        step="0.1"
        value={draft.weight_kg}
        onChange={(weight_kg) => set({ weight_kg })}
      />
    </div>
  );
}

export function LevelField({ draft, set }: FieldsProps) {
  return (
    <fieldset>
      <legend className="mb-3 text-sm font-medium text-slate-700">
        Which best describes your swimming?
      </legend>
      <div className="grid gap-3 sm:grid-cols-2">
        {SWIM_LEVELS.map((level) => {
          const on = draft.swim_level === level.value;
          return (
            <label
              key={level.value}
              className={`cursor-pointer rounded-xl border p-4 transition ${
                on
                  ? "border-sky-600 bg-sky-50 ring-4 ring-sky-600/10"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <input
                type="radio"
                name="swim_level"
                value={level.value}
                checked={on}
                onChange={() => set({ swim_level: level.value })}
                className="sr-only"
              />
              <span className="block font-medium text-slate-900">{level.label}</span>
              <span className="text-sm text-slate-500">{level.note}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

const SESSION_CHOICES = ["1", "2", "3", "4", "5", "6", "7", "8", "10"];
const MINUTE_CHOICES = ["30", "45", "60", "90", "120"];

export function TrainingFields({ draft, set }: FieldsProps) {
  return (
    <div className="space-y-6">
      <div>
        <NumberField
          label="How many times do you train a week?"
          unit="times"
          placeholder="4"
          value={draft.sessions_per_week}
          onChange={(sessions_per_week) => set({ sessions_per_week })}
        />
        <div className="mt-2.5 flex flex-wrap gap-2">
          {SESSION_CHOICES.map((n) => (
            <Chip
              key={n}
              on={draft.sessions_per_week === n}
              onClick={() => set({ sessions_per_week: n })}
            >
              {n}
            </Chip>
          ))}
        </div>
      </div>
      <div>
        <NumberField
          label="How much time do you spend swimming each day?"
          unit="min"
          placeholder="60"
          value={draft.minutes_per_day}
          onChange={(minutes_per_day) => set({ minutes_per_day })}
        />
        <div className="mt-2.5 flex flex-wrap gap-2">
          {MINUTE_CHOICES.map((m) => (
            <Chip
              key={m}
              on={draft.minutes_per_day === m}
              onClick={() => set({ minutes_per_day: m })}
            >
              {Number(m) < 60 ? `${m} min` : `${Number(m) / 60} h`}
            </Chip>
          ))}
        </div>
      </div>
    </div>
  );
}

const newPb = (): PbDraft => ({ event: "", pool: "25 m", time: "" });

export function PbFields({ draft, set }: FieldsProps) {
  const rows = draft.pbs.length ? draft.pbs : [newPb()];
  function update(i: number, changes: Partial<PbDraft>) {
    set({ pbs: rows.map((row, j) => (j === i ? { ...row, ...changes } : row)) });
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Optional. Add your best times if you have them; skip this if you don&apos;t race.
      </p>
      <ul className="space-y-3">
        {rows.map((row, i) => (
          <li
            key={i}
            className="grid grid-cols-[1fr_auto] items-end gap-2 rounded-xl bg-sky-50/60 p-3 sm:grid-cols-[1.4fr_1fr_1fr_auto]"
          >
            <label className="col-span-2 block space-y-1 sm:col-span-1">
              <span className="block text-xs font-medium text-slate-600">Event</span>
              <select
                value={row.event}
                onChange={(e) => update(i, { event: e.target.value })}
                className={inputClass}
              >
                <option value="">Choose event</option>
                {PB_EVENTS.map((ev) => (
                  <option key={ev}>{ev}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="block text-xs font-medium text-slate-600">Pool</span>
              <select
                value={row.pool}
                onChange={(e) => update(i, { pool: e.target.value })}
                className={inputClass}
              >
                {PB_POOLS.map((pool) => (
                  <option key={pool}>{pool}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="block text-xs font-medium text-slate-600">Time</span>
              <input
                inputMode="decimal"
                placeholder="1:02.30"
                value={row.time}
                onChange={(e) => update(i, { time: e.target.value })}
                className={inputClass}
              />
            </label>
            <button
              type="button"
              onClick={() => set({ pbs: rows.filter((_, j) => j !== i) })}
              aria-label="Remove this time"
              className="col-start-2 row-start-1 self-start rounded-lg px-2 py-1 text-lg text-slate-400 hover:bg-surface hover:text-slate-700 sm:col-start-auto sm:row-start-auto sm:self-end sm:py-2.5"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      {rows.length < MAX_PBS && (
        <button
          type="button"
          onClick={() => set({ pbs: [...rows, newPb()] })}
          className="text-sm font-semibold text-sky-700 hover:text-sky-900"
        >
          + Add another time
        </button>
      )}
    </div>
  );
}
