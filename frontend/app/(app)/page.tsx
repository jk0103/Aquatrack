"use client";

import Link from "next/link";

import { useUser } from "@/app/components/AppShell";
import { ChevronIcon, TrophyIcon, UploadIcon } from "@/app/components/icons";
import { TimeChart } from "@/app/components/TimeChart";
import { Badge, Card, CardLink, DateChip, LaneProgress, Stat } from "@/app/components/ui";
import {
  analyses,
  events,
  formatDate,
  formatTime,
  progression,
  TODAY,
  trainingPlans,
} from "@/app/lib/mock";

export default function HomePage() {
  const user = useUser();
  const firstName = user?.name.split(" ")[0];
  const upcoming = events.filter((e) => e.date >= TODAY).slice(0, 4);
  const nextMeet = events.find((e) => e.kind === "Meet" && e.date >= TODAY);
  const latest = analyses.find((a) => a.status === "Ready")!;
  const free100 = progression["100 m Freestyle"];
  const best = Math.min(...free100.map((e) => e.seconds));

  return (
    <>
      {/* Hero: a pool-coloured banner with the main action */}
      <section className="relative mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-sky-800 via-sky-700 to-cyan-600 p-6 text-white shadow-sm sm:mb-8 sm:p-8">
        <div className="relative z-10 max-w-xl">
          <p className="text-sm text-sky-100">{formatDate(TODAY, { weekday: "long" })}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            {firstName ? `Welcome back, ${firstName}` : "Welcome back"}
          </h1>
          <p className="mt-2 text-sky-100">
            {nextMeet
              ? `${nextMeet.title} is on ${formatDate(nextMeet.date)}. Upload a swim to see what to work on before then.`
              : "Upload a swim to get feedback on your technique."}
          </p>
          <Link
            href="/analyze"
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-sky-800 shadow-sm hover:bg-sky-50"
          >
            <UploadIcon className="h-4 w-4" />
            Analyze a swim
          </Link>
        </div>
        <svg
          aria-hidden="true"
          viewBox="0 0 400 120"
          preserveAspectRatio="none"
          className="absolute inset-x-0 bottom-0 h-24 w-full text-white/10"
        >
          {[40, 80, 120].map((y) => (
            <path
              key={y}
              d={`M0 ${y} Q50 ${y - 12} 100 ${y} T200 ${y} T300 ${y} T400 ${y}`}
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
            />
          ))}
        </svg>
      </section>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:mb-8 sm:gap-4 lg:grid-cols-4">
        <Stat label="100 m free best" value={formatTime(best)} note="−3.5 s since May" />
        <Stat label="Technique score" value={`${latest.score}`} note="+4 from last month" />
        <Stat label="Swims analyzed" value={`${analyses.length}`} />
        <Stat label="Sessions this week" value="2 of 5" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          title="Training in progress"
          action={<CardLink href="/training">All plans</CardLink>}
          className="lg:col-span-2"
        >
          <ul className="space-y-5">
            {trainingPlans.map((plan) => (
              <li key={plan.id}>
                <div className="mb-2 flex items-baseline justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900">{plan.name}</p>
                    <p className="truncate text-sm text-slate-500">Next: {plan.next}</p>
                  </div>
                  <span className="shrink-0 text-sm text-slate-500">
                    {plan.done}/{plan.total}
                  </span>
                </div>
                <LaneProgress value={(plan.done / plan.total) * 100} label={`${plan.name} progress`} />
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Coming up" action={<CardLink href="/calendar">Calendar</CardLink>}>
          <ul className="divide-y divide-slate-100">
            {upcoming.map((e) => (
              <li key={e.date + e.title} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                <DateChip iso={e.date} meet={e.kind === "Meet"} />
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-900">{e.title}</p>
                  <p className="text-sm text-slate-500">
                    {e.kind === "Meet" ? (
                      <span className="inline-flex items-center gap-1 text-indigo-700">
                        <TrophyIcon className="h-3.5 w-3.5" /> Meet
                      </span>
                    ) : (
                      "Training"
                    )}{" "}
                    · {e.time}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card
          title="100 m freestyle"
          action={<CardLink href="/progress">Progress</CardLink>}
          className="lg:col-span-2"
        >
          <TimeChart entries={free100} goal={60} compact />
        </Card>

        <Card title="Latest feedback" action={<CardLink href="/history">History</CardLink>}>
          <Link href={`/feedback/${latest.id}`} className="group block">
            <div className="mb-3 flex flex-wrap gap-2">
              <Badge>{latest.stroke}</Badge>
              <Badge tone="slate">{latest.camera}</Badge>
            </div>
            <p className="font-medium text-slate-900 group-hover:text-sky-800">{latest.headline}</p>
            <p className="mt-1 text-sm text-slate-500">
              {formatDate(latest.date)} · Score {latest.score}
            </p>
            <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-sky-700">
              View feedback <ChevronIcon className="h-4 w-4" />
            </span>
          </Link>
        </Card>
      </div>
    </>
  );
}
