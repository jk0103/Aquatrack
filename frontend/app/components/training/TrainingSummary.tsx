"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useUser } from "@/app/components/AppShell";
import { Badge, Card, LoadingState, Stat } from "@/app/components/ui";
import {
  byDate,
  formatDay,
  localIso,
  sessionMeta,
  statusLabel,
  statusTone,
  weekDates,
  type CalendarFeed,
  type TrainingOverview,
} from "@/app/lib/training";
import { fetchCalendar, fetchTraining } from "@/app/lib/trainingApi";

function useTraining() {
  const uid = useUser()?.uid;
  const [view, setView] = useState<TrainingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!uid) return;
    let live = true;
    fetchTraining().then((res) => {
      if (!live) return;
      if (res.ok) setView(res.data);
      else setError(res.error);
    });
    return () => {
      live = false;
    };
  }, [uid]);
  return { view, error, uid };
}

// Home: the swimmer's real week and what is coming up. No example data.
export function TrainingThisWeek() {
  const { view, error, uid } = useTraining();
  const [today] = useState(() => localIso(new Date()));
  const [feed, setFeed] = useState<CalendarFeed | null>(null);
  const days = weekDates(today);
  const [from, to] = [days[0], days[6]];
  useEffect(() => {
    if (!uid) return;
    let live = true;
    fetchCalendar(from, to).then((res) => live && res.ok && setFeed(res.data));
    return () => {
      live = false;
    };
  }, [uid, from, to]);
  const sessions = byDate(feed?.sessions ?? []);
  const rest = new Set((feed?.rest_days ?? []).map((d) => d.date));

  return (
    <Card
      title="Your training this week"
      action={
        <Link href="/calendar" className="text-sm font-medium text-sky-700 hover:text-sky-900">
          Open calendar
        </Link>
      }
    >
      {error && (
        <p role="alert" className="text-sm text-red-700">
          Couldn&apos;t load your training. {error}
        </p>
      )}
      {!view && !error && <LoadingState label="Loading your training…" />}
      {view && (
        <>
          <ol className="grid grid-cols-7 gap-1 sm:gap-2">
            {days.map((day) => {
              const list = (sessions.get(day) ?? []).filter((s) => s.status !== "canceled");
              const isToday = day === today;
              return (
                <li key={day}>
                  <Link
                    href={`/calendar?date=${day}`}
                    aria-current={isToday ? "date" : undefined}
                    className={`flex min-h-20 flex-col items-center rounded-xl px-1 py-2 text-center ${
                      isToday ? "bg-sky-700 text-white" : "bg-slate-50 text-slate-800 hover:bg-slate-100"
                    }`}
                  >
                    <span className={`text-xs font-semibold ${isToday ? "text-sky-100" : "text-slate-500"}`}>
                      {formatDay(day, { weekday: "short" })}
                    </span>
                    <span className="text-lg font-semibold tabular-nums">{Number(day.slice(8))}</span>
                    <span className={`mt-auto text-[11px] leading-tight ${isToday ? "text-sky-50" : "text-slate-600"}`}>
                      {list.length
                        ? list.every((s) => s.status === "completed")
                          ? "Done"
                          : list.some((s) => s.status === "planned")
                            ? `${list.length} planned`
                            : statusLabel(list[0].status)
                        : rest.has(day)
                          ? "Rest"
                          : ""}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ol>
          <p className="mt-3 text-sm text-slate-600">
            {view.week.completed} completed, {view.week.planned} still planned, {view.week.skipped}{" "}
            skipped this week.
          </p>
          {view.upcoming.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {view.upcoming.slice(0, 3).map((s) => (
                <li key={s.id}>
                  <Link
                    href={`/calendar?date=${s.date}`}
                    className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2.5 hover:bg-slate-100"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-900">{s.title}</span>
                      <span className="block text-xs text-slate-500">
                        {formatDay(s.date)}
                        {s.time ? ` · ${s.time}` : ""} · {sessionMeta(s)}
                      </span>
                    </span>
                    <Badge tone="sky">Upcoming</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-slate-600">
              No sessions planned.{" "}
              <Link href="/training" className="font-medium text-sky-700 hover:text-sky-900">
                Make a training plan
              </Link>
            </p>
          )}
        </>
      )}
    </Card>
  );
}

// Progress: what the swimmer practised, kept visibly apart from what their videos measure.
export function TrainingProgress() {
  const { view, error } = useTraining();
  if (error || !view) return null; // the measured progress above stands on its own
  const recent = view.history.filter((s) => s.status === "completed").slice(0, 5);
  return (
    <Card
      title="Training you recorded"
      action={
        <Link href="/training" className="text-sm font-medium text-sky-700 hover:text-sky-900">
          Training
        </Link>
      }
    >
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Completed this week" value={String(view.week.completed)} />
        <Stat label="Planned this week" value={String(view.week.planned)} />
        <Stat label="Completed in total" value={String(view.totals.completed)} />
        <Stat label="Skipped in total" value={String(view.totals.skipped)} />
      </div>
      {recent.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-100">
          {recent.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-2">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-slate-900">{s.title}</span>
                <span className="block text-xs text-slate-500">
                  {s.completion ? formatDay(s.completion.completed_on) : formatDay(s.date)} ·{" "}
                  {s.items.filter((i) => i.done).length} of {s.items.length} activities
                </span>
              </span>
              <Badge tone={statusTone(s.status)}>{statusLabel(s.status)}</Badge>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Entered by you. This shows practice you recorded, not a technique measurement, and a
        change measured in a later video is never attributed to it.
      </p>
    </Card>
  );
}
