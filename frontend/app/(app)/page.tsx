"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useUser } from "@/app/components/AppShell";
import {
  ChartIcon,
  ChevronIcon,
  HistoryIcon,
  UploadIcon,
  VideoIcon,
} from "@/app/components/icons";
import { TimeChart } from "@/app/components/TimeChart";
import { TrainingThisWeek } from "@/app/components/training/TrainingSummary";
import {
  Badge,
  ExampleNote,
  GlassCard,
  LoadingState,
} from "@/app/components/ui";
import { describeFirebaseError } from "@/app/lib/firebase";
import {
  analyses,
  progression,
} from "@/app/lib/mock";
import { listVideos, statusLabel, statusTone, videoDate, type VideoRecord } from "@/app/lib/videos";

import heroPhoto from "@/public/images/hero-butterfly.jpg";

export default function HomePage() {
  const user = useUser();
  const firstName = user?.name.split(" ")[0];
  const [uploads, setUploads] = useState<VideoRecord[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const uid = user?.uid;
  useEffect(() => {
    if (!uid) return;
    listVideos(uid)
      .then(setUploads)
      .catch((err) => setLoadError(describeFirebaseError(err)));
  }, [uid]);
  const realToday = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
  const latest = analyses.find((a) => a.status === "Ready")!;

  return (
    <div className="space-y-5 lg:space-y-6">
      <section className="relative min-h-[280px] overflow-hidden rounded-2xl bg-sky-950 p-6 text-white shadow-sm sm:p-8">
        {/* Butterfly swimmer photo, on the right so the text stays clear */}
        <div className="absolute inset-y-0 right-0 w-full md:w-[68%] md:[mask-image:linear-gradient(to_right,transparent,black_40%)]">
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
          <p className="text-sm text-sky-100" suppressHydrationWarning>
            {realToday}
          </p>
          <h1 className="mt-1 text-4xl font-semibold tracking-tight sm:text-5xl">
            {firstName ? `Welcome back, ${firstName}` : "Welcome back"}
          </h1>
          <p className="mt-3 text-sky-50/90">
            {uploads?.length
              ? `You've uploaded ${uploads.length} ${uploads.length === 1 ? "swim" : "swims"}. Add another to keep building your history.`
              : "Upload a swim to start your history and get ready for technique feedback."}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/analyze"
              className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-semibold text-[#075985] shadow-md transition duration-300 hover:-translate-y-0.5 hover:shadow-lg"
            >
              <UploadIcon className="h-4 w-4" />
              Analyze a swim
            </Link>
            <Link
              href={uploads?.length ? `/history/${uploads[0].id}` : `/feedback/${latest.id}`}
              className="inline-flex items-center gap-2 rounded-full bg-white/10 px-5 py-3 text-sm font-semibold text-white ring-1 ring-white/25 transition duration-300 hover:-translate-y-0.5 hover:bg-white/25"
            >
              {uploads?.length ? "Latest upload" : "See example feedback"}
            </Link>
          </div>
        </div>
      </section>

      <RecentUploads uploads={uploads} error={loadError} />

      <TrainingThisWeek />

      <ExampleNote>
        Everything below is example data: the times and feedback aren&apos;t yours yet.
      </ExampleNote>

      {/* Two stacked columns, so a short card never leaves a gap beside a tall one */}
      <div className="grid items-start gap-5 lg:grid-cols-3 lg:gap-6">
        <div className="min-w-0 space-y-5 lg:col-span-2 lg:space-y-6">
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
          <GlassCard
            title="Example feedback"
            icon={<VideoIcon className="h-5 w-5" />}
            href={`/feedback/${latest.id}`}
            linkLabel="Open example feedback"
            glow="rgb(45 212 191 / 0.14)"
          >
            <div className="flex items-end gap-3">
              <p className="font-display text-5xl font-semibold tracking-tight text-slate-900 tabular-nums">
                {latest.score}
              </p>
              <p className="pb-1 text-sm font-medium text-teal-700">+4 this month</p>
            </div>
            <p className="mt-1 truncate text-sm text-slate-600">{latest.headline}</p>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}

// The swimmer's own uploads from Firestore: how many, and the latest few.
function RecentUploads({
  uploads,
  error,
}: {
  uploads: VideoRecord[] | null;
  error: string | null;
}) {
  const waiting =
    uploads?.filter((v) => ["uploaded", "queued", "analyzing"].includes(v.status)).length ?? 0;
  return (
    <GlassCard
      title="Your uploads"
      icon={<HistoryIcon className="h-5 w-5" />}
      href="/history"
      linkLabel="All uploads"
    >
      {error ? (
        <p role="alert" className="text-sm text-red-700">
          Couldn&apos;t load your uploads. {error}
        </p>
      ) : uploads === null ? (
        <LoadingState label="Loading your uploads…" />
      ) : uploads.length === 0 ? (
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-600">
            No swims yet. Upload a video and it will show up here and in History.
          </p>
          <Link
            href="/analyze"
            className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-sky-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-sky-800"
          >
            <UploadIcon className="h-4 w-4" /> Upload your first swim
          </Link>
        </div>
      ) : (
        <>
          <p className="-mt-2 mb-3 text-sm text-slate-500">
            {uploads.length} {uploads.length === 1 ? "video" : "videos"} uploaded
            {waiting ? ` · ${waiting} waiting for analysis` : ""}
          </p>
          <ul className="grid gap-3 sm:grid-cols-3">
            {uploads.slice(0, 3).map((v) => (
              <li key={v.id} className="min-w-0">
                <Link
                  href={`/history/${v.id}`}
                  className="group flex h-full items-center gap-3 rounded-2xl bg-slate-50 p-3 transition duration-300 hover:-translate-y-0.5 hover:bg-slate-100"
                >
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-b from-sky-700 to-cyan-800 text-white/85">
                    <svg
                      viewBox="0 0 24 24"
                      className="h-5 w-5"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path d="M8 5.5v13l10-6.5z" />
                    </svg>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-slate-900 group-hover:text-sky-800">
                      {[v.distance, v.stroke].filter(Boolean).join(" ")}
                    </span>
                    <span className="block truncate text-xs text-slate-500">
                      {videoDate(v)?.toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      }) ?? "Just now"}{" "}
                      · {v.camera}
                    </span>
                    <span className="mt-1 block">
                      <Badge tone={statusTone[v.status]}>{statusLabel[v.status]}</Badge>
                    </span>
                  </span>
                  <ChevronIcon className="h-4 w-4 shrink-0 text-slate-500 group-hover:text-sky-700" />
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </GlassCard>
  );
}
