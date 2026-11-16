"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { useUser } from "@/app/components/AppShell";
import { ChevronIcon } from "@/app/components/icons";
import { SessionCard } from "@/app/components/training/SessionCard";
import { SessionEditor } from "@/app/components/training/SessionEditor";
import { Badge, Button, ButtonLink, Card, LoadingState, PageHeader } from "@/app/components/ui";
import {
  addDays,
  byDate,
  formatDay,
  isIsoDate,
  localIso,
  monthGrid,
  monthTitle,
  sessionMeta,
  statusLabel,
  statusTone,
  weekDates,
  type Activity,
  type CalendarFeed,
  type TrainingSession,
} from "@/app/lib/training";
import { createSession, fetchCalendar, fetchTraining } from "@/app/lib/trainingApi";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DOT: Record<TrainingSession["status"], string> = {
  planned: "bg-sky-600",
  completed: "bg-teal-500",
  skipped: "bg-amber-500",
  canceled: "bg-slate-400",
  replaced: "bg-slate-300",
};

export default function CalendarPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading…" />}>
      <Calendar />
    </Suspense>
  );
}

function Calendar() {
  const user = useUser();
  const uid = user?.uid;
  const asked = useSearchParams().get("date") ?? "";
  // The swimmer's own clock decides what "today" is. Read once, on the client.
  const [today] = useState(() => localIso(new Date()));
  const [selected, setSelected] = useState(isIsoDate(asked) ? asked : today);
  const [mode, setMode] = useState<"month" | "week">("month");
  const [feed, setFeed] = useState<CalendarFeed | null>(null);
  const [library, setLibrary] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const [year, month] = [Number(selected.slice(0, 4)), Number(selected.slice(5, 7)) - 1];
  const rows = useMemo(
    () => (mode === "month" ? monthGrid(year, month) : [weekDates(selected)]),
    [mode, year, month, selected],
  );
  const from = rows[0][0];
  const to = rows[rows.length - 1][6];

  const reload = useCallback(() => {
    if (!uid) return;
    fetchCalendar(from, to).then((res) => {
      if (res.ok) {
        setFeed(res.data);
        setError(null);
      } else setError(res.error);
    });
  }, [uid, from, to]);
  useEffect(reload, [reload]);
  useEffect(() => {
    if (!uid) return;
    fetchTraining().then((res) => res.ok && setLibrary(res.data.library));
  }, [uid]);

  const sessions = useMemo(() => byDate(feed?.sessions ?? []), [feed]);
  const rest = useMemo(() => byDate(feed?.rest_days ?? []), [feed]);
  const dayOf = sessions.get(selected) ?? [];
  const upcoming = (feed?.sessions ?? []).filter(
    (s) => s.status === "planned" && s.date >= today,
  );

  function move(step: number) {
    setAdding(false);
    if (mode === "week") return setSelected(addDays(selected, 7 * step));
    const target = new Date(year, month + step, 1, 12);
    const last = new Date(target.getFullYear(), target.getMonth() + 1, 0, 12).getDate();
    const day = Math.min(Number(selected.slice(8, 10)), last);
    setSelected(localIso(new Date(target.getFullYear(), target.getMonth(), day, 12)));
  }

  return (
    <>
      <PageHeader
        title="Calendar"
        subtitle="Your planned and recorded swimming sessions."
        action={<ButtonLink href="/training">Make a plan</ButtonLink>}
      />
      {error && (
        <p role="alert" className="mb-4 text-sm text-red-700">
          Couldn&apos;t load your calendar. {error}
        </p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-slate-900" aria-live="polite">
              {mode === "month"
                ? monthTitle(year, month)
                : `${formatDay(from, { month: "short", day: "numeric" })} – ${formatDay(to, { month: "short", day: "numeric", year: "numeric" })}`}
            </h2>
            <div className="flex items-center gap-1.5">
              <div className="mr-1 flex rounded-lg border border-slate-300 p-0.5" role="group" aria-label="Calendar view">
                {(["month", "week"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    aria-pressed={mode === m}
                    onClick={() => setMode(m)}
                    className={`rounded-md px-2.5 py-1.5 text-sm font-medium capitalize ${
                      mode === m ? "bg-sky-700 text-white" : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => move(-1)}
                aria-label={mode === "month" ? "Previous month" : "Previous week"}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
              >
                <ChevronIcon className="h-5 w-5 rotate-180" />
              </button>
              <Button variant="secondary" onClick={() => setSelected(today)}>
                Today
              </Button>
              <button
                type="button"
                onClick={() => move(1)}
                aria-label={mode === "month" ? "Next month" : "Next week"}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
              >
                <ChevronIcon className="h-5 w-5" />
              </button>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-7 gap-1 text-center text-xs font-semibold text-slate-500">
            {WEEKDAYS.map((d) => (
              <div key={d} className="py-1">
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {rows.flat().map((day) => {
              const list = sessions.get(day) ?? [];
              const inMonth = mode === "week" || Number(day.slice(5, 7)) - 1 === month;
              const isSelected = day === selected;
              const label =
                formatDay(day, { weekday: "long", month: "long", day: "numeric" }) +
                (list.length
                  ? `, ${list.length} ${list.length === 1 ? "session" : "sessions"}`
                  : rest.has(day)
                    ? ", rest day"
                    : "");
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => {
                    setSelected(day);
                    setAdding(false);
                  }}
                  aria-label={label}
                  aria-current={day === today ? "date" : undefined}
                  aria-pressed={isSelected}
                  className={`flex flex-col items-center rounded-xl px-0.5 py-1.5 text-sm transition ${
                    mode === "week" ? "min-h-24" : "min-h-14 sm:min-h-16"
                  } ${
                    isSelected
                      ? "bg-sky-700 text-white"
                      : day === today
                        ? "bg-sky-50 font-semibold text-sky-800 ring-1 ring-sky-300"
                        : inMonth
                          ? "text-slate-800 hover:bg-slate-100"
                          : "text-slate-400 hover:bg-slate-50"
                  }`}
                >
                  <span className="tabular-nums">{Number(day.slice(8, 10))}</span>
                  <span className="mt-1 flex flex-wrap justify-center gap-0.5">
                    {list.slice(0, 4).map((s) => (
                      <span
                        key={s.id}
                        aria-hidden="true"
                        className={`h-1.5 w-1.5 rounded-full ${isSelected ? "bg-white" : DOT[s.status]}`}
                      />
                    ))}
                  </span>
                  {mode === "week" &&
                    list.slice(0, 2).map((s) => (
                      <span
                        key={s.id}
                        className="mt-1 hidden w-full truncate px-1 text-[11px] leading-tight sm:block"
                      >
                        {s.title}
                      </span>
                    ))}
                  {list.length === 0 && rest.has(day) && (
                    <span className={`mt-0.5 text-[10px] ${isSelected ? "text-sky-100" : "text-slate-400"}`}>
                      rest
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
            {(["planned", "completed", "skipped", "canceled"] as const).map((s) => (
              <li key={s} className="flex items-center gap-1.5">
                <span aria-hidden="true" className={`h-2 w-2 rounded-full ${DOT[s]}`} />
                {statusLabel(s)}
              </li>
            ))}
          </ul>
          {!feed && !error && <LoadingState label="Loading your sessions…" />}
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card
            title={formatDay(selected, { weekday: "long", month: "long", day: "numeric" })}
            action={
              !adding ? (
                <Button variant="secondary" onClick={() => setAdding(true)}>
                  Add a session
                </Button>
              ) : undefined
            }
          >
            {adding && (
              <div className="mb-4 rounded-2xl border border-slate-200 p-4">
                <p className="mb-3 text-sm text-slate-600">
                  A session you create is yours: nothing in it is marked as recommended.
                </p>
                <SessionEditor
                  initial={{ date: selected, time: "", title: "", items: [] }}
                  library={library}
                  submitLabel="Add to calendar"
                  onCancel={() => setAdding(false)}
                  onSubmit={async (draft) => {
                    const res = await createSession(draft);
                    if (!res.ok) return res.error;
                    setAdding(false);
                    setSelected(res.data.date);
                    reload();
                    return null;
                  }}
                />
              </div>
            )}
            {dayOf.length === 0 && !adding && (
              <p className="text-sm text-slate-600">
                {rest.has(selected)
                  ? `Rest day in your plan. ${rest.get(selected)![0].guidance}`
                  : "Nothing scheduled on this day."}
              </p>
            )}
            <div className="space-y-3">
              {dayOf.map((s) => (
                <SessionCard
                  key={s.id + s.status + s.items.length}
                  session={s}
                  library={library}
                  videos={feed?.videos ?? []}
                  onChanged={reload}
                />
              ))}
            </div>
          </Card>

          <Card title="Coming up in this view">
            {upcoming.length === 0 ? (
              <p className="text-sm text-slate-600">
                No planned sessions from today in this {mode}.{" "}
                <Link href="/training" className="font-medium text-sky-700 hover:text-sky-900">
                  Make a plan
                </Link>
              </p>
            ) : (
              <ul className="space-y-2">
                {upcoming.slice(0, 6).map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(s.date)}
                      className="flex w-full items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2.5 text-left hover:bg-slate-100"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-slate-900">
                          {s.title}
                        </span>
                        <span className="block text-xs text-slate-500">
                          {formatDay(s.date)}
                          {s.time ? ` · ${s.time}` : ""} · {sessionMeta(s)}
                        </span>
                      </span>
                      <Badge tone={statusTone(s.status)}>{statusLabel(s.status)}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
