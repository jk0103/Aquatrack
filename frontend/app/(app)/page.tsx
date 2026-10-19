"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { useUser } from "@/app/components/AppShell";
import {
  CalendarIcon,
  ChartIcon,
  PlanIcon,
  TrophyIcon,
  UploadIcon,
  VideoIcon,
} from "@/app/components/icons";
import { TimeChart } from "@/app/components/TimeChart";
import { DateChip, GlassCard, LaneProgress } from "@/app/components/ui";
import {
  analyses,
  events,
  formatDate,
  progression,
  TODAY,
  trainingPlans,
  type CalendarEvent,
} from "@/app/lib/mock";

const DAY = 24 * 60 * 60 * 1000;

function isoDay(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Monday to Sunday of the week containing TODAY.
function thisWeek() {
  const today = new Date(`${TODAY}T00:00:00`);
  const monday = new Date(today.getTime() - ((today.getDay() + 6) % 7) * DAY);
  return Array.from({ length: 7 }, (_, i) => isoDay(new Date(monday.getTime() + i * DAY)));
}

export default function HomePage() {
  const user = useUser();
  const firstName = user?.name.split(" ")[0];
  const week = thisWeek();
  const weekEnd = week[6];
  const upcoming = events.filter((e) => e.date > weekEnd).slice(0, 4);
  const nextMeet = events.find((e) => e.kind === "Meet" && e.date >= TODAY);
  const daysToMeet = nextMeet
    ? Math.round(
        (new Date(`${nextMeet.date}T00:00:00`).getTime() -
          new Date(`${TODAY}T00:00:00`).getTime()) /
          DAY,
      )
    : null;
  const latest = analyses.find((a) => a.status === "Ready")!;

  return (
    <div className="relative isolate">
      <WaterBackdrop />

      <div className="grid gap-5 lg:grid-cols-3 lg:gap-6">
        {/* Hero */}
        <section className="relative min-h-[260px] overflow-hidden rounded-2xl bg-gradient-to-br from-sky-800 via-sky-700 to-cyan-600 p-6 text-white shadow-sm sm:p-8 lg:col-span-2">
          <Caustics />
          <SwimmerArt />
          <div className="relative z-10 max-w-md">
            <p className="text-sm text-sky-100">{formatDate(TODAY, { weekday: "long" })}</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">
              {firstName ? `Welcome back, ${firstName}` : "Welcome back"}
            </h1>
            <p className="mt-3 text-sky-50/90">
              {nextMeet
                ? `${nextMeet.title} is ${daysToMeet === 0 ? "today" : `in ${daysToMeet} days`}. Upload a swim to see what to sharpen before race day.`
                : "Upload a swim to get feedback on your technique."}
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/analyze"
                className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-[#075985] shadow-md transition duration-300 hover:-translate-y-0.5 hover:shadow-lg"
              >
                <UploadIcon className="h-4 w-4" />
                Analyze a swim
              </Link>
              <Link
                href={`/feedback/${latest.id}`}
                className="inline-flex items-center gap-2 rounded-full bg-white/10 px-5 py-2.5 text-sm font-semibold text-white ring-1 ring-white/25 transition duration-300 hover:-translate-y-0.5 hover:bg-white/25"
              >
                Latest feedback
              </Link>
            </div>
          </div>
        </section>

        {/* Two glass tiles beside the hero */}
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-1 lg:gap-6">
          {nextMeet && (
            <GlassCard
              title="Next meet"
              icon={<TrophyIcon className="h-5 w-5" />}
              href="/calendar"
              linkLabel="Open calendar"
              glow="rgb(129 140 248 / 0.16)"
            >
              <p className="text-xl font-semibold tracking-tight text-slate-900">
                {nextMeet.title}
              </p>
              <p className="mt-1 text-sm text-slate-600">
                {formatDate(nextMeet.date, { weekday: "short" })} · {nextMeet.time}
              </p>
              <p className="mt-3 inline-flex rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700">
                {daysToMeet === 0 ? "Today" : `In ${daysToMeet} days`}
              </p>
            </GlassCard>
          )}
          <GlassCard
            title="Latest feedback"
            icon={<VideoIcon className="h-5 w-5" />}
            href={`/feedback/${latest.id}`}
            linkLabel="Open feedback"
            glow="rgb(45 212 191 / 0.14)"
          >
            <div className="flex items-end gap-3">
              <p className="text-4xl font-semibold tracking-tight text-slate-900">{latest.score}</p>
              <p className="pb-1 text-sm font-medium text-teal-700">+4 this month</p>
            </div>
            <p className="mt-1 truncate text-sm text-slate-600">{latest.headline}</p>
          </GlassCard>
        </div>

        {/* Left: this week, then what's after it */}
        <div className="min-w-0 space-y-5 lg:col-span-2 lg:space-y-6">
          <GlassCard
            title="This week"
            icon={<CalendarIcon className="h-5 w-5" />}
            href="/calendar"
            linkLabel="Open calendar"
          >
            <WeekStrip days={week} />
          </GlassCard>

          <GlassCard title="Coming up" icon={<CalendarIcon className="h-5 w-5" />}>
            <p className="-mt-2 mb-3 text-sm text-slate-500">After this week</p>
            <ul className="grid gap-3 sm:grid-cols-2">
              {upcoming.map((e) => (
                <li
                  key={e.date + e.title}
                  className="flex items-center gap-3 rounded-2xl bg-slate-50 p-3 transition duration-300 hover:-translate-y-0.5 hover:bg-slate-100"
                >
                  <DateChip iso={e.date} meet={e.kind === "Meet"} />
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900">{e.title}</p>
                    <p className="truncate text-sm text-slate-500">
                      {e.kind === "Meet" ? "Meet" : "Training"} · {e.time}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </GlassCard>
        </div>

        {/* Right: training and times */}
        <div className="min-w-0 space-y-5 lg:space-y-6">
          <GlassCard
            title="Training"
            icon={<PlanIcon className="h-5 w-5" />}
            href="/training"
            linkLabel="All plans"
          >
            <ul className="space-y-4">
              {trainingPlans.map((plan) => (
                <li key={plan.id}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3">
                    <p className="truncate text-sm font-medium text-slate-900">{plan.name}</p>
                    <span className="shrink-0 text-xs text-slate-500">
                      {plan.done}/{plan.total}
                    </span>
                  </div>
                  <LaneProgress
                    value={(plan.done / plan.total) * 100}
                    label={`${plan.name} progress`}
                  />
                </li>
              ))}
            </ul>
          </GlassCard>

          <GlassCard
            title="100 m freestyle"
            icon={<ChartIcon className="h-5 w-5" />}
            href="/progress"
            linkLabel="Progress"
          >
            <TimeChart entries={progression["100 m Freestyle"]} goal={60} compact />
          </GlassCard>
        </div>
      </div>
    </div>
  );
}

// Seven day columns for the current week, with today highlighted.
function WeekStrip({ days }: { days: string[] }) {
  // On narrow screens the strip scrolls sideways; start with today in view.
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    const today = el?.querySelector<HTMLElement>("[data-today]");
    if (el && today && el.scrollWidth > el.clientWidth) {
      el.scrollLeft = today.offsetLeft - (el.clientWidth - today.offsetWidth) / 2;
    }
  }, []);
  return (
    <div ref={scroller} className="relative -mx-1 overflow-x-auto px-1 pt-1 pb-2">
      <ol className="grid min-w-[560px] grid-cols-7 gap-2">
        {days.map((iso) => {
          const d = new Date(`${iso}T00:00:00`);
          const isToday = iso === TODAY;
          const past = iso < TODAY;
          const dayEvents = events.filter((e) => e.date === iso);
          return (
            <li key={iso} data-today={isToday || undefined}>
              <Link
                href="/calendar"
                className={`flex h-full min-h-[132px] flex-col rounded-2xl p-2.5 transition duration-300 hover:-translate-y-0.5 ${
                  isToday ? "bg-sky-700 text-white shadow-sm" : "bg-slate-50 hover:bg-slate-100"
                } ${past ? "opacity-70" : ""}`}
              >
                <span
                  className={`text-xs font-semibold uppercase ${isToday ? "text-sky-100" : "text-slate-500"}`}
                >
                  {d.toLocaleDateString("en-US", { weekday: "short" })}
                </span>
                <span
                  className={`text-xl font-semibold ${isToday ? "text-white" : "text-slate-900"}`}
                >
                  {d.getDate()}
                </span>
                <span className="mt-auto space-y-1.5 pt-2">
                  {dayEvents.length ? (
                    dayEvents.map((e) => (
                      <WeekEvent key={e.title} event={e} onToday={isToday} done={past} />
                    ))
                  ) : (
                    <span
                      className={`block text-xs ${isToday ? "text-sky-100" : "text-slate-400"}`}
                    >
                      Rest
                    </span>
                  )}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function WeekEvent({
  event,
  onToday,
  done,
}: {
  event: CalendarEvent;
  onToday: boolean;
  done: boolean;
}) {
  const meet = event.kind === "Meet";
  const tone = onToday
    ? "bg-white/20 text-white"
    : meet
      ? "bg-indigo-50 text-indigo-700"
      : "bg-sky-50 text-sky-800";
  return (
    <span className={`block rounded-lg px-2 py-1 text-[11px] leading-tight font-medium ${tone}`}>
      <span className="block truncate">
        {done && !meet ? "✓ " : ""}
        {event.title}
      </span>
      <span className="block opacity-75">{event.time}</span>
    </span>
  );
}

// Soft, slowly drifting colour behind the glass so it has something to blur.
function WaterBackdrop() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute -inset-x-4 -top-6 -bottom-6 -z-10 overflow-hidden sm:-inset-x-8"
    >
      <div className="drift absolute top-[-6%] left-[8%] h-[420px] w-[420px] rounded-full bg-sky-300/25 blur-3xl dark:bg-sky-500/10" />
      <div className="drift-slow absolute top-[30%] right-[-4%] h-[460px] w-[460px] rounded-full bg-cyan-300/20 blur-3xl dark:bg-cyan-400/[0.06]" />
      <div className="drift absolute bottom-[-8%] left-[30%] h-[380px] w-[380px] rounded-full bg-indigo-300/15 blur-3xl dark:bg-indigo-500/[0.08]" />
    </div>
  );
}

// Light rippling across a pool floor.
function Caustics() {
  return (
    <svg
      aria-hidden="true"
      className="absolute inset-0 h-full w-full text-white/[0.08]"
      viewBox="0 0 400 200"
      preserveAspectRatio="none"
    >
      {[30, 70, 110, 150, 190].map((y, i) => (
        <path
          key={y}
          className={i % 2 ? "drift-slow" : "drift"}
          d={`M-20 ${y} Q30 ${y - 16} 80 ${y} T180 ${y} T280 ${y} T380 ${y} T480 ${y}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        />
      ))}
    </svg>
  );
}

// A freestyle swimmer gliding through the hero, drawn simply.
function SwimmerArt() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 320 160"
      className="absolute right-[-30px] bottom-2 hidden w-[52%] max-w-[420px] text-white/60 md:block"
    >
      <circle cx="252" cy="70" r="15" fill="currentColor" />
      <path
        d="M236 74 C200 80 160 86 120 84 C96 83 78 80 60 76"
        fill="none"
        stroke="currentColor"
        strokeWidth="16"
        strokeLinecap="round"
      />
      <path
        d="M228 70 C252 52 278 46 306 48"
        fill="none"
        stroke="currentColor"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <path
        d="M200 84 C190 104 172 116 150 120"
        fill="none"
        stroke="currentColor"
        strokeWidth="9"
        strokeLinecap="round"
        opacity="0.7"
      />
      <path
        d="M64 76 C46 70 30 72 14 78 M66 82 C48 92 32 96 16 96"
        fill="none"
        stroke="currentColor"
        strokeWidth="8"
        strokeLinecap="round"
        opacity="0.8"
      />
      <path
        d="M0 104 Q40 94 80 104 T160 104 T240 104 T320 104"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        opacity="0.5"
      />
    </svg>
  );
}
