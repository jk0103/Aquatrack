"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { useUser } from "@/app/components/AppShell";
import { CalendarIcon, ChartIcon, PlanIcon, UploadIcon, VideoIcon } from "@/app/components/icons";
import { TimeChart } from "@/app/components/TimeChart";
import { ArcGauge, DateChip, GlassCard } from "@/app/components/ui";
import {
  analyses,
  events,
  formatDate,
  progression,
  TODAY,
  trainingPlans,
  type CalendarEvent,
} from "@/app/lib/mock";

import heroPhoto from "@/public/images/hero-butterfly.jpg";

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
    <div className="space-y-5 lg:space-y-6">
      <section className="relative min-h-[280px] overflow-hidden rounded-2xl bg-sky-950 p-6 text-white shadow-sm sm:p-8">
        {/* Butterfly swimmer photo, on the right so the text stays clear */}
        <div className="absolute inset-y-0 right-0 w-full md:w-[68%]">
          <Image
            src={heroPhoto}
            placeholder="blur"
            alt=""
            fill
            priority
            sizes="(min-width: 1024px) 50vw, 100vw"
            className="object-cover object-[center_45%]"
          />
        </div>
        {/* Darkens the left side so the text stays readable over the photo */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-r from-sky-950 via-sky-950/70 via-45% to-transparent"
        />
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

      <GlassCard
        title="This week"
        icon={<CalendarIcon className="h-5 w-5" />}
        href="/calendar"
        linkLabel="Open calendar"
      >
        <WeekStrip days={week} />
      </GlassCard>

      {/* Two stacked columns, so a short card never leaves a gap beside a tall one */}
      <div className="grid items-start gap-5 lg:grid-cols-3 lg:gap-6">
        <div className="min-w-0 space-y-5 lg:col-span-2 lg:space-y-6">
          <GlassCard
            title="Training in progress"
            icon={<PlanIcon className="h-5 w-5" />}
            href="/training"
            linkLabel="All plans"
          >
            <ul className="grid grid-cols-3 gap-2 sm:gap-4">
              {trainingPlans.map((plan) => (
                <li key={plan.id} className="min-w-0 text-center">
                  <ArcGauge value={(plan.done / plan.total) * 100} label={`${plan.name} progress`}>
                    <p className="text-lg font-semibold tracking-tight text-slate-900 sm:text-2xl">
                      {plan.done}
                      <span className="text-sm font-medium text-slate-400 sm:text-base">
                        /{plan.total}
                      </span>
                    </p>
                    <p className="text-[11px] text-slate-500">sessions</p>
                  </ArcGauge>
                  <p className="-mt-2 truncate text-sm font-medium text-slate-900">{plan.name}</p>
                  <p className="text-xs text-slate-500">
                    Week {plan.week} of {plan.weeks}
                  </p>
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
        <div className="min-w-0 space-y-5 lg:space-y-6">
          <GlassCard title="Coming up" icon={<CalendarIcon className="h-5 w-5" />}>
            <p className="-mt-2 mb-3 text-sm text-slate-500">After this week</p>
            <ul className="space-y-3">
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
                  isToday
                    ? "bg-sky-700 text-white shadow-sm"
                    : "bg-surface ring-1 ring-slate-300/80 shadow-sm hover:ring-sky-400"
                } ${past ? "opacity-80" : ""}`}
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
