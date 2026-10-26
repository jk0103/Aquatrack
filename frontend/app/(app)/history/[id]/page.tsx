"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useUser } from "@/app/components/AppShell";
import { FeedbackStage } from "@/app/components/FeedbackStage";
import { ChevronIcon } from "@/app/components/icons";
import { Badge, ButtonLink, Card, LoadingState } from "@/app/components/ui";
import { VideoPlayer } from "@/app/components/VideoPlayer";
import { describeFirebaseError } from "@/app/lib/firebase";
import { formatSwimTime } from "@/app/lib/profile";
import {
  formatBytes,
  formatDuration,
  getVideo,
  getVideoUrl,
  statusLabel,
  statusTone,
  videoDate,
  type VideoRecord,
} from "@/app/lib/videos";

// One of the swimmer's own uploads: the real video from Storage, what they told us about the
// swim, and where analysis stands. Example feedback lives at /feedback/[id] instead.
export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  // undefined while loading, null when there's no such video.
  const [video, setVideo] = useState<VideoRecord | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);

  const uid = user?.uid;
  useEffect(() => {
    if (!uid || !id) return;
    let live = true;
    getVideo(id)
      .then(async (record) => {
        if (!live) return;
        setVideo(record);
        if (!record) return;
        try {
          const link = await getVideoUrl(record);
          if (live) setUrl(link);
        } catch (err) {
          const code = (err as { code?: string })?.code;
          if (live)
            setUrlError(
              code === "storage/object-not-found"
                ? "The video file is missing from storage."
                : describeFirebaseError(err),
            );
        }
      })
      .catch((err) => {
        if (!live) return;
        const code = (err as { code?: string })?.code;
        // Someone else's video reads as permission-denied; treat it like a missing one.
        if (code === "permission-denied") setVideo(null);
        else setLoadError(describeFirebaseError(err));
      });
    return () => {
      live = false;
    };
  }, [uid, id]);

  const back = (
    <nav className="mb-4 text-sm">
      <Link href="/history" className="text-sky-700 hover:text-sky-900">
        History
      </Link>
      {video && (
        <>
          <span className="mx-2 text-slate-500">/</span>
          <span className="text-slate-500">{video.fileName}</span>
        </>
      )}
    </nav>
  );

  if (loadError) {
    return (
      <>
        {back}
        <p
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700"
        >
          Couldn&apos;t load this video. {loadError}
        </p>
      </>
    );
  }
  if (video === undefined) {
    return (
      <>
        {back}
        <LoadingState label="Loading your video…" />
      </>
    );
  }
  if (video === null) {
    return (
      <div className="mx-auto max-w-lg py-10 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Video not found</h1>
        <p className="mt-2 text-slate-600">
          It may have been removed, or it belongs to another account.
        </p>
        <div className="mt-6 flex justify-center">
          <ButtonLink href="/history">Back to history</ButtonLink>
        </div>
      </div>
    );
  }

  const date = videoDate(video);
  const session = {
    stroke: video.stroke,
    distance: video.distance,
    camera: video.camera,
  };
  const player = urlError ? (
    <p
      role="alert"
      className="flex aspect-video items-center justify-center rounded-3xl bg-slate-100 px-6 text-center text-sm text-slate-600"
    >
      Couldn&apos;t open the video. {urlError}
    </p>
  ) : url ? (
    <VideoPlayer
      src={url}
      label={`${video.distance} ${video.stroke} video`}
      durationHint={video.durationSeconds}
    />
  ) : (
    <div className="flex aspect-video items-center justify-center rounded-3xl bg-slate-100">
      <LoadingState label="Getting the video…" />
    </div>
  );

  return (
    <>
      {back}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="indigo">Your upload</Badge>
            <Badge tone={statusTone[video.status]}>{statusLabel[video.status]}</Badge>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            {[video.distance, video.stroke].filter(Boolean).join(" ")}
          </h1>
          <p className="mt-1.5 text-slate-600">
            {date
              ? date.toLocaleDateString("en-US", {
                  weekday: "long",
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })
              : "Date not recorded"}{" "}
            · {video.camera}
          </p>
        </div>
      </div>

      {video.status === "ready" && video.analysis ? (
        <FeedbackStage
          source="analysis"
          session={session}
          result={video.analysis}
          videoUrl={url}
          aside={<SessionCard video={video} />}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-3">
            {player}
            <AnalysisStatus video={video} />
          </div>
          <div className="lg:col-span-2">
            <SessionCard video={video} />
          </div>
        </div>
      )}
    </>
  );
}

function AnalysisStatus({ video }: { video: VideoRecord }) {
  const text = {
    uploaded:
      "Your video is uploaded but hasn't been analyzed yet. Technique analysis is still being connected; when it runs, the feedback will appear on this page.",
    analyzing: "Your video is being analyzed. Feedback will appear on this page when it's done.",
    ready:
      "Analysis finished, but its results couldn't be shown. This page will update once the results format is supported.",
    failed: "Analysis couldn't finish for this video. Your upload is still saved.",
  }[video.status];
  return (
    <Card title="Technique feedback">
      <p className="text-sm text-slate-600">{text}</p>
      <p className="mt-3 text-sm text-slate-600">
        Want to see what feedback will look like?{" "}
        <Link
          href="/feedback/a-1042"
          className="inline-flex items-center gap-0.5 font-medium text-sky-700 hover:text-sky-900"
        >
          Open an example analysis <ChevronIcon className="h-4 w-4" />
        </Link>
      </p>
    </Card>
  );
}

function SessionCard({ video }: { video: VideoRecord }) {
  const rows: [string, string | undefined][] = [
    ["Stroke", video.stroke],
    ["Filming angle", video.camera],
    ["Distance in clip", video.distance || undefined],
    ["Pool length", video.poolLength],
    ["Time", video.timeSeconds !== undefined ? formatSwimTime(video.timeSeconds) : undefined],
    [
      "Swim date",
      video.sessionDate
        ? new Date(`${video.sessionDate}T00:00:00`).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          })
        : undefined,
    ],
    [
      "Uploaded",
      video.createdAt?.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }),
    ],
    [
      "File",
      `${formatBytes(video.sizeBytes)}${video.durationSeconds ? ` · ${formatDuration(video.durationSeconds)}` : ""}`,
    ],
  ];
  const asked = [
    video.wantFeedback && "Technique feedback",
    video.wantPlan && "Training plan suggestion",
  ].filter(Boolean);
  return (
    <Card title="Session details">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd
              className={`mt-0.5 text-sm ${value ? "font-medium text-slate-900" : "text-slate-500"}`}
            >
              {value ?? "Not given"}
            </dd>
          </div>
        ))}
      </dl>
      {asked.length > 0 && (
        <p className="mt-4 text-sm text-slate-600">
          <span className="font-medium text-slate-700">You asked for: </span>
          {asked.join(" and ")}
        </p>
      )}
      {video.comments && (
        <blockquote className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
          <p className="mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">
            Session notes
          </p>
          “{video.comments}”
        </blockquote>
      )}
      <div className="mt-5">
        <Link
          href="/history"
          className="inline-flex items-center gap-1 text-sm font-semibold text-sky-700 hover:text-sky-900"
        >
          <ChevronIcon className="h-4 w-4 rotate-180" /> Back to history
        </Link>
      </div>
    </Card>
  );
}
