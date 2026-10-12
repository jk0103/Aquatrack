"use client";

import { useState } from "react";

import { TextField } from "@/app/components/fields";
import { profile } from "@/app/lib/mock";

// Profile questions, shared by the signup survey and the edit profile page.

const selectClass =
  "block w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm focus:border-sky-600 focus:outline-none focus:ring-4 focus:ring-sky-600/15";

type Defaults = Partial<typeof profile>;

function Chips({
  label,
  options,
  multiple = false,
  initial = [],
}: {
  label: string;
  options: string[];
  multiple?: boolean;
  initial?: string[];
}) {
  const [picked, setPicked] = useState<string[]>(initial);
  function toggle(option: string) {
    setPicked((p) =>
      multiple
        ? p.includes(option)
          ? p.filter((o) => o !== option)
          : [...p, option]
        : [option],
    );
  }
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-slate-700">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const on = picked.includes(option);
          return (
            <button
              key={option}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(option)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                on
                  ? "bg-sky-700 text-white shadow-sm"
                  : "border border-slate-300 bg-white text-slate-700 hover:border-sky-400"
              }`}
            >
              {option}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function Select({ label, options, defaultValue }: { label: string; options: string[]; defaultValue?: string }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-medium text-slate-700">{label}</span>
      <select className={selectClass} defaultValue={defaultValue ?? ""}>
        <option value="" disabled>
          Choose one
        </option>
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}

export function AboutFields({ d = {} }: { d?: Defaults }) {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <TextField label="Year of birth" inputMode="numeric" placeholder="2005" defaultValue={d.birthYear} />
      <Select label="Gender" options={["Female", "Male", "Non-binary", "Prefer not to say"]} />
      <div className="sm:col-span-2">
        <TextField label="Club or team" placeholder="Optional" defaultValue={d.club} />
      </div>
    </div>
  );
}

export function SwimmingFields({ d = {} }: { d?: Defaults }) {
  return (
    <div className="space-y-6">
      <Chips
        label="How would you describe your swimming?"
        options={["Learning", "Fitness", "Masters", "Competitive (club)", "Elite"]}
        initial={d.level ? [d.level] : []}
      />
      <Chips
        label="Which strokes do you swim? Pick all that apply."
        options={["Freestyle", "Backstroke", "Breaststroke", "Butterfly"]}
        multiple
        initial={d.strokes}
      />
      <div className="grid gap-5 sm:grid-cols-2">
        <Select label="Usual pool" options={["25 m", "25 yd", "50 m", "Open water"]} defaultValue={d.poolLength} />
        <Select
          label="Sessions per week"
          options={["1", "2", "3", "4", "5", "6+"]}
          defaultValue={d.sessionsPerWeek ? String(d.sessionsPerWeek) : undefined}
        />
      </div>
    </div>
  );
}

export function GoalFields({ d = {} }: { d?: Defaults }) {
  return (
    <div className="space-y-6">
      <Chips
        label="What do you want to improve?"
        options={["Speed", "Technique", "Endurance", "Starts & turns", "Race prep"]}
        multiple
        initial={d.goal ? ["Speed", "Technique"] : []}
      />
      <label className="block space-y-1.5">
        <span className="block text-sm font-medium text-slate-700">Your main goal</span>
        <textarea
          rows={3}
          className={`${selectClass} resize-y`}
          placeholder="e.g. Break 1:00 in the 100 m freestyle by spring"
          defaultValue={d.goal}
        />
      </label>
    </div>
  );
}

export function TimesFields() {
  const rows = [
    ["50 m Freestyle", "28.10"],
    ["100 m Freestyle", "1:01.30"],
    ["50 m Butterfly", "31.80"],
  ];
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        Optional. Your best times help us track progress and set realistic targets.
      </p>
      {rows.map(([event, time]) => (
        <div key={event} className="grid grid-cols-[1fr_8rem] items-center gap-3">
          <span className="text-sm font-medium text-slate-800">{event}</span>
          <input className={selectClass} placeholder={time} aria-label={`${event} best time`} />
        </div>
      ))}
      <button type="button" className="text-sm font-semibold text-sky-700 hover:text-sky-900">
        + Add another event
      </button>
    </div>
  );
}
