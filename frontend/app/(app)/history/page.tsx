"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useUser } from "@/app/components/AppShell";
import { ChevronIcon } from "@/app/components/icons";
import { Badge, ButtonLink, PageHeader } from "@/app/components/ui";
import { describeFirebaseError } from "@/app/lib/firebase";
import { analyses, formatDate } from "@/app/lib/mock";
import { listVideos, type VideoRecord } from "@/app/lib/videos";

const strokes = ["All strokes", "Freestyle", "Backstroke", "Breaststroke", "Butterfly"];

export default function HistoryPage() {
  const user = useUser();
  const [stroke, setStroke] = useState(strokes[0]);
  const [uploads, setUploads] = useState<VideoRecord[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const uid = user?.uid;
  useEffect(() => {
    if (!uid) return;
    listVideos(uid)
      .then(setUploads)
      .catch((err) => setLoadError(describeFirebaseError(err)));
  }, [uid]);
  const myUploads = (uploads ?? []).filter((v) => stroke === strokes[0] || v.stroke === stroke);
  const list = [...analyses]
    .filter((a) => stroke === strokes[0] || a.stroke === stroke)
    .sort((a, b) => b.date.localeCompare(a.date));

  return (
    <>
      <PageHeader
        title="History"
        subtitle="Every swim you've uploaded and the feedback you got."
        action={<ButtonLink href="/analyze">Analyze a swim</ButtonLink>}
      />

      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-slate-500">
          {myUploads.length} {myUploads.length === 1 ? "upload" : "uploads"}
        </p>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <span className="sr-only">Stroke</span>
          <select
            value={stroke}
            onChange={(e) => setStroke(e.target.value)}
            className="rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-sky-600 focus:outline-none focus:ring-4 focus:ring-sky-600/15"
          >
            {strokes.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>

      {loadError && <p className="mb-4 text-sm text-red-700">{loadError}</p>}
      {uploads === null && !loadError ? (
        <p className="mb-8 text-sm text-slate-500">Loading your uploads…</p>
      ) : myUploads.length ? (
        <ul className="mb-10 space-y-3">
          {myUploads.map((v) => (
            <li
              key={v.id}
              className="flex items-center gap-4 rounded-2xl glass p-3 sm:p-4"
            >
              <div className="relative flex h-16 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-b from-sky-700 to-cyan-800 text-white/80 sm:h-20 sm:w-32">
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor" aria-hidden="true">
                  <path d="M8 5.5v13l10-6.5z" />
                </svg>
                <span className="absolute bottom-1 left-1 rounded bg-black/40 px-1.5 text-[10px] text-white">
                  {v.distance}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <Badge>{v.stroke}</Badge>
                  <span className="hidden sm:inline">
                    <Badge tone="slate">{v.camera}</Badge>
                  </span>
                  <Badge tone="amber">Waiting for analysis</Badge>
                </div>
                <p className="truncate font-medium text-slate-900">{v.fileName}</p>
                <p className="truncate text-sm text-slate-500">
                  {v.createdAt
                    ? v.createdAt.toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })
                    : "Just now"}
                  {v.comments ? ` · “${v.comments}”` : ""}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-8 rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          No uploads yet. Your videos will show up here.
        </p>
      )}

      <h2 className="mb-1 font-semibold text-slate-900">Example analyses</h2>
      <p className="mb-4 text-sm text-slate-500">
        Sample results showing what feedback will look like.
      </p>
      <ul className="space-y-3">
        {list.map((a) => (
          <li key={a.id}>
            <Link
              href={`/feedback/${a.id}`}
              className="group flex items-center gap-4 rounded-2xl glass p-3 transition duration-300 hover:-translate-y-0.5 hover:shadow-md sm:p-4"
            >
              <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg bg-gradient-to-b from-sky-700 to-cyan-800 sm:h-20 sm:w-32">
                <svg viewBox="0 0 120 80" className="absolute inset-0 h-full w-full text-white/15" aria-hidden="true">
                  <path d="M0 30 Q15 24 30 30 T60 30 T90 30 T120 30M0 55 Q15 49 30 55 T60 55 T90 55 T120 55" fill="none" stroke="currentColor" strokeWidth="3" />
                </svg>
                <span className="absolute bottom-1 left-1 rounded bg-black/40 px-1.5 text-[10px] text-white">
                  {a.distance}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <Badge>{a.stroke}</Badge>
                  <span className="hidden sm:inline">
                    <Badge tone="slate">{a.camera}</Badge>
                  </span>
                  {a.status === "Processing" && <Badge tone="amber">Processing</Badge>}
                </div>
                <p className="truncate font-medium text-slate-900 group-hover:text-sky-800">{a.headline}</p>
                <p className="text-sm text-slate-500">{formatDate(a.date, { year: "numeric" })}</p>
              </div>
              {a.status === "Ready" && (
                <div className="hidden text-right sm:block">
                  <p className="text-2xl font-semibold text-slate-900">{a.score}</p>
                  <p className="text-xs text-slate-500">score</p>
                </div>
              )}
              <ChevronIcon className="h-5 w-5 shrink-0 text-slate-500 group-hover:text-sky-700" />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
