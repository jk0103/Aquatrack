"use client";

import { useState } from "react";

import { TimeChart } from "@/app/components/TimeChart";
import { Card, ExampleNote, PageHeader, Stat } from "@/app/components/ui";
import { formatDate, formatTime, progression } from "@/app/lib/mock";

const goals: Record<string, number> = {
  "100 m Freestyle": 60,
  "50 m Freestyle": 27.5,
  "50 m Butterfly": 31,
};

export default function ProgressPage() {
  const names = Object.keys(progression);
  const [event, setEvent] = useState(names[0]);
  const entries = progression[event];
  const first = entries[0];
  const latest = entries[entries.length - 1];
  const best = Math.min(...entries.map((e) => e.seconds));
  const goal = goals[event];

  return (
    <>
      <PageHeader title="Progress" subtitle="How your times are dropping over the season." />
      <div className="mb-6">
        <ExampleNote>
          These times are examples. Your own times will appear here as you log them.
        </ExampleNote>
      </div>

      <div className="mb-6 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Event">
        {names.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={event === name}
            onClick={() => setEvent(name)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition ${
              event === name
                ? "bg-sky-700 text-white shadow-sm"
                : "border border-slate-300 bg-surface text-slate-600 hover:bg-slate-50"
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat label="Personal best" value={formatTime(best)} />
        <Stat
          label="Improvement"
          value={`−${(first.seconds - latest.seconds).toFixed(2)} s`}
          note={`since ${formatDate(first.date)}`}
        />
        <Stat
          label="Goal"
          value={formatTime(goal)}
          note={`${(latest.seconds - goal).toFixed(2)} s to go`}
        />
        <Stat label="Swims logged" value={`${entries.length}`} />
      </div>

      <Card
        title={event}
        action={
          <div className="flex gap-4 text-xs text-slate-600">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full border-2 border-sky-700 bg-surface" />{" "}
              Practice
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-indigo-600" /> Meet
            </span>
          </div>
        }
        className="mb-6"
      >
        <p className="-mt-2 mb-3 text-xs text-slate-500">Faster times are higher on the chart.</p>
        <TimeChart entries={entries} goal={goal} />
      </Card>

      <Card title="All times">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="py-2 pr-4 font-medium">Date</th>
                <th className="py-2 pr-4 font-medium">Time</th>
                <th className="py-2 pr-4 font-medium">Type</th>
                <th className="py-2 font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {[...entries].reverse().map((e, i, list) => {
                const prev = list[i + 1];
                const diff = prev ? e.seconds - prev.seconds : null;
                return (
                  <tr key={e.date} className="border-b border-slate-100 last:border-0">
                    <td className="py-2.5 pr-4 text-slate-700">
                      {formatDate(e.date, { year: "numeric" })}
                    </td>
                    <td className="py-2.5 pr-4 font-medium text-slate-900">
                      {formatTime(e.seconds)}
                    </td>
                    <td className="py-2.5 pr-4 text-slate-600">{e.meet ? "Meet" : "Practice"}</td>
                    <td
                      className={`py-2.5 ${diff === null ? "text-slate-500" : diff < 0 ? "text-teal-700" : "text-amber-700"}`}
                    >
                      {diff === null
                        ? "—"
                        : `${diff < 0 ? "−" : "+"}${Math.abs(diff).toFixed(2)} s`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
