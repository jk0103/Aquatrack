"use client";

import { useState } from "react";

import { ChevronIcon, TrophyIcon } from "@/app/components/icons";
import { Button, Card, DateChip, PageHeader } from "@/app/components/ui";
import { events, formatDate, TODAY, type CalendarEvent } from "@/app/lib/mock";

const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const filters = ["All", "Training", "Meet"] as const;

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function monthDays(year: number, month: number) {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7; // Monday first
  const days: (Date | null)[] = Array.from({ length: offset }, () => null);
  const count = new Date(year, month + 1, 0).getDate();
  for (let d = 1; d <= count; d++) days.push(new Date(year, month, d));
  while (days.length % 7) days.push(null);
  return days;
}

export default function CalendarPage() {
  const [month, setMonth] = useState(() => new Date(`${TODAY}T00:00:00`));
  const [selected, setSelected] = useState(TODAY);
  const [filter, setFilter] = useState<(typeof filters)[number]>("All");

  const shown = events.filter((e) => filter === "All" || e.kind === filter);
  const byDate = new Map<string, CalendarEvent[]>();
  for (const e of shown) byDate.set(e.date, [...(byDate.get(e.date) ?? []), e]);
  const days = monthDays(month.getFullYear(), month.getMonth());
  const selectedEvents = byDate.get(selected) ?? [];
  const meets = events.filter((e) => e.kind === "Meet" && e.date >= TODAY);

  function shiftMonth(delta: number) {
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() + delta, 1));
  }

  return (
    <>
      <PageHeader
        title="Calendar"
        subtitle="Training sessions and upcoming competitions in one place."
        action={<Button>Add event</Button>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1">
              <button
                onClick={() => shiftMonth(-1)}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
                aria-label="Previous month"
              >
                <ChevronIcon className="h-5 w-5 rotate-180" />
              </button>
              <h2 className="min-w-36 text-center font-semibold text-slate-900">
                {month.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
              </h2>
              <button
                onClick={() => shiftMonth(1)}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
                aria-label="Next month"
              >
                <ChevronIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="flex rounded-lg bg-slate-100 p-1 text-sm" role="group" aria-label="Show">
              {filters.map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  aria-pressed={filter === f}
                  className={`rounded-md px-3 py-1.5 font-medium ${
                    filter === f ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
                  }`}
                >
                  {f === "Meet" ? "Meets" : f}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-7 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200">
            {weekdays.map((d) => (
              <div key={d} className="bg-slate-50 py-2 text-center text-xs font-semibold text-slate-500">
                <span className="sm:hidden">{d[0]}</span>
                <span className="hidden sm:inline">{d}</span>
              </div>
            ))}
            {days.map((d, i) => {
              if (!d) return <div key={i} className="min-h-14 bg-white sm:min-h-24" />;
              const key = iso(d);
              const dayEvents = byDate.get(key) ?? [];
              const isToday = key === TODAY;
              const isSelected = key === selected;
              return (
                <button
                  key={key}
                  onClick={() => setSelected(key)}
                  className={`flex min-h-14 flex-col items-stretch gap-1 bg-white p-1 text-left transition hover:bg-sky-50/60 sm:min-h-24 sm:p-1.5 ${
                    isSelected ? "ring-2 ring-inset ring-sky-600" : ""
                  }`}
                >
                  <span
                    className={`flex h-6 w-6 items-center justify-center self-center rounded-full text-xs sm:self-start ${
                      isToday ? "bg-sky-700 font-semibold text-white" : "text-slate-700"
                    }`}
                  >
                    {d.getDate()}
                  </span>
                  {/* Dots on phones, labels on larger screens */}
                  <span className="flex justify-center gap-1 sm:hidden">
                    {dayEvents.map((e) => (
                      <span
                        key={e.title}
                        className={`h-1.5 w-1.5 rounded-full ${e.kind === "Meet" ? "bg-indigo-500" : "bg-sky-500"}`}
                      />
                    ))}
                  </span>
                  {dayEvents.map((e) => (
                    <span
                      key={e.title}
                      className={`hidden truncate rounded px-1.5 py-0.5 text-[11px] font-medium sm:block ${
                        e.kind === "Meet" ? "bg-indigo-100 text-indigo-800" : "bg-sky-100 text-sky-800"
                      }`}
                    >
                      {e.title}
                    </span>
                  ))}
                </button>
              );
            })}
          </div>

          <div className="mt-4 flex gap-5 text-xs text-slate-600">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-sky-500" /> Training
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-indigo-500" /> Competition / meet
            </span>
          </div>
        </Card>

        <div className="space-y-6">
          <Card title={formatDate(selected, { weekday: "long" })}>
            {selectedEvents.length ? (
              <ul className="space-y-3">
                {selectedEvents.map((e) => (
                  <EventRow key={e.title} event={e} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">Nothing planned. A good day for recovery.</p>
            )}
          </Card>

          <Card title="Upcoming meets">
            <ul className="space-y-4">
              {meets.map((e) => (
                <li key={e.date} className="flex items-center gap-3">
                  <DateChip iso={e.date} meet />
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900">{e.title}</p>
                    <p className="truncate text-sm text-slate-500">
                      {e.place} · {e.time}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}

function EventRow({ event }: { event: CalendarEvent }) {
  const meet = event.kind === "Meet";
  return (
    <li
      className={`rounded-xl border-l-4 p-3 ${meet ? "border-indigo-500 bg-indigo-50" : "border-sky-500 bg-sky-50"}`}
    >
      <p className="flex items-center gap-1.5 font-medium text-slate-900">
        {meet && <TrophyIcon className="h-4 w-4 text-indigo-600" />}
        {event.title}
      </p>
      <p className="text-sm text-slate-600">
        {event.time}
        {event.place ? ` · ${event.place}` : ""}
      </p>
    </li>
  );
}
