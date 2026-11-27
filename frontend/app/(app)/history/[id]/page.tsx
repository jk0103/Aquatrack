"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AnalysisPanel } from "@/app/components/AnalysisPanel";
import { SavedPoseNotice } from "@/app/components/DemoNotice";
import { FeedbackPanel } from "@/app/components/FeedbackPanel";
import { InterpretationPanel } from "@/app/components/InterpretationPanel";
import {
  ProblemFrameStage,
  ResultPills,
} from "@/app/components/ProblemFrameStage";
import {
  NextVideoCard,
  ResultFeedbackCard,
  SuggestedPlanCard,
} from "@/app/components/ResultLower";
import { useUser } from "@/app/components/AppShell";
import { ChevronIcon } from "@/app/components/icons";
import { Badge, ButtonLink, Card, LoadingState } from "@/app/components/ui";
import { VideoPlayer } from "@/app/components/VideoPlayer";
import { loadAnalysis } from "@/app/lib/analysisLoad";
import type { AnalysisV1 } from "@/app/lib/analysisV1";
import type { Feedback } from "@/app/lib/feedback";
import { loadFeedback } from "@/app/lib/feedbackLoad";
import type { Interpretation } from "@/app/lib/interpretation";
import { loadInterpretation } from "@/app/lib/interpretationLoad";
import { describeFirebaseError } from "@/app/lib/firebase";
import { deleteVideo } from "@/app/lib/historyApi";
import { formatSwimTime } from "@/app/lib/profile";
import { framesForPriorities } from "@/app/lib/problemFrames";
import {
  loadProblemFrames,
  type LoadedFrames,
} from "@/app/lib/problemFramesLoad";
import {
  formatBytes,
  formatDuration,
  getVideoUrl,
  statusLabel,
  statusTone,
  videoDate,
  watchVideo,
  type VideoRecord,
} from "@/app/lib/videos";

// One of the swimmer's own uploads: the real video from Storage, what they told us about the
// swim, where analysis stands, and its real results. The record is watched live, so status
// changes made by the backend appear without a reload. Example feedback lives at
// /feedback/[id] instead.
export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  // undefined while loading, null when there's no such video.
  const [video, setVideo] = useState<VideoRecord | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);
  // The loaded result, tagged with the run it belongs to so a re-run never shows old numbers.
  const [loaded, setLoaded] = useState<{
    analysisId: string;
    result: AnalysisV1 | null;
    error: string | null;
  } | null>(null);

  const uid = user?.uid;
  useEffect(() => {
    if (!uid || !id) return;
    return watchVideo(id, setVideo, (err) => {
      const code = (err as { code?: string })?.code;
      // Someone else's video reads as permission-denied; treat it like a missing one.
      if (code === "permission-denied") setVideo(null);
      else setLoadError(describeFirebaseError(err));
    });
  }, [uid, id]);

  const storagePath = video?.storagePath;
  useEffect(() => {
    if (!video || !storagePath) return;
    let live = true;
    getVideoUrl(video)
      .then((link) => live && setUrl(link))
      .catch((err) => {
        const code = (err as { code?: string })?.code;
        if (live)
          setUrlError(
            code === "storage/object-not-found"
              ? "The video file is missing from storage."
              : describeFirebaseError(err),
          );
      });
    return () => {
      live = false;
    };
    // The link only depends on where the file is, not on the rest of the record.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storagePath]);

  const analysisId = video?.status === "ready" ? video.latestAnalysisId : null;
  useEffect(() => {
    if (!id || !analysisId) return;
    let live = true;
    loadAnalysis(id, analysisId)
      .then((result) => live && setLoaded({ analysisId, result, error: null }))
      .catch(
        (err) =>
          live &&
          setLoaded({
            analysisId,
            result: null,
            error: describeFirebaseError(err),
          }),
      );
    return () => {
      live = false;
    };
  }, [id, analysisId]);
  const current = loaded && loaded.analysisId === analysisId ? loaded : null;
  // undefined while loading; null when the stored result can't be read.
  const analysis = current ? current.result : undefined;
  const analysisError = current?.error ?? null;

  // The interpretation is a separate document. If it is missing or unreadable the
  // measurements below still show; findings are simply not shown.
  const interpretationId =
    video?.status === "ready" ? video.latestInterpretationId : null;
  const [found, setFound] = useState<{
    id: string;
    value: Interpretation | null;
  } | null>(null);
  useEffect(() => {
    if (!id || !interpretationId) return;
    let live = true;
    loadInterpretation(id, interpretationId)
      .then((value) => live && setFound({ id: interpretationId, value }))
      .catch(() => live && setFound({ id: interpretationId, value: null }));
    return () => {
      live = false;
    };
  }, [id, interpretationId]);
  const interpretation =
    found && found.id === interpretationId ? found.value : null;

  // Feedback (Phase 4) is built from the interpretation and stored as its own document.
  // Videos analysed before it existed have none and show the interpretation instead.
  const feedbackId = video?.status === "ready" ? video.latestFeedbackId : null;
  const [fb, setFb] = useState<{ id: string; value: Feedback | null } | null>(
    null,
  );
  useEffect(() => {
    if (!id || !feedbackId) return;
    let live = true;
    loadFeedback(id, feedbackId)
      .then((value) => live && setFb({ id: feedbackId, value }))
      .catch(() => live && setFb({ id: feedbackId, value: null }));
    return () => {
      live = false;
    };
  }, [id, feedbackId]);
  const feedback = fb && fb.id === feedbackId ? fb.value : null;

  // Frames from the video that show the feedback's priorities, stored per feedback document.
  const [fr, setFr] = useState<{
    id: string;
    value: LoadedFrames | null;
  } | null>(null);
  useEffect(() => {
    if (!id || !feedbackId) return;
    let live = true;
    loadProblemFrames(id, feedbackId)
      .then((value) => live && setFr({ id: feedbackId, value }))
      .catch(() => live && setFr({ id: feedbackId, value: null }));
    return () => {
      live = false;
    };
  }, [id, feedbackId]);
  // undefined while loading
  const loadedFrames = !feedbackId
    ? null
    : fr && fr.id === feedbackId
      ? fr.value
      : undefined;
  const priorities = (feedback?.items ?? [])
    .filter((i) => i.category === "priority")
    .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));
  const mainFix = priorities[0] ?? null;
  const frames =
    loadedFrames && loadedFrames !== null
      ? {
          ...loadedFrames,
          frames: framesForPriorities(
            loadedFrames,
            priorities.map((p) => p.id),
          ),
        }
      : loadedFrames;

  function seek(seconds: number) {
    const player = document.querySelector<HTMLVideoElement>("main video");
    if (!player) return;
    player.currentTime = seconds;
    player.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function playFrom(seconds: number) {
    seek(seconds);
    void document.querySelector<HTMLVideoElement>("main video")?.play();
  }

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
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          Video not found
        </h1>
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

  // A finished analysis: the example page's layout and motion, filled from the real result.
  if (video.status === "ready" && analysis) {
    const dateText = date
      ? date.toLocaleDateString("en-US", {
          weekday: "long",
          month: "short",
          day: "numeric",
          year: "numeric",
        })
      : "Date not recorded";
    const hasFrames = !!frames && frames.frames.length > 0;
    return (
      <>
        {back}
        <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
              {mainFix ? mainFix.title : "No main fix from this clip"}
            </h1>
            <p className="mt-1.5 text-slate-600">
              {[dateText, [video.stroke, video.distance].filter(Boolean).join(" "), video.camera]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
        </div>
        <div className="mb-5">
          <ResultPills analysis={analysis} />
        </div>
        {/* Saved pose data is not a model run on this upload: say so where it is seen, not
            only inside the folded details below. */}
        {analysis.poseSource === "precomputed" && (
          <div className="mb-4">
            <SavedPoseNotice />
          </div>
        )}
        <ProblemFrameStage
          video={video}
          analysis={analysis}
          mainFix={mainFix}
          frames={frames}
          videoUrl={url}
          onPlayFrom={playFrom}
        />
        {/* Below the stage, as on the example page: feedback card and plan card */}
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="min-w-0 space-y-6 lg:col-span-3">
            {feedback ? (
              <ResultFeedbackCard feedback={feedback} comment={video.comments || undefined} />
            ) : (
              interpretation && (
                <InterpretationPanel
                  interpretation={interpretation}
                  onSeek={url ? seek : undefined}
                />
              )
            )}
            {/* The stage shows the video itself when there are no frames */}
            {hasFrames && player}
          </div>
          <div className="min-w-0 space-y-6 lg:col-span-2">
            <SuggestedPlanCard videoId={video.id} />
            {feedback && <NextVideoCard feedback={feedback} />}
            <SessionCard video={video} />
          </div>
        </div>
        <details className="group mt-6 rounded-2xl glass p-5 sm:p-6">
          <summary className="cursor-pointer text-sm font-semibold text-slate-900">
            Full analysis details
          </summary>
          <div className="mt-5 space-y-6">
            {feedback && <FeedbackPanel feedback={feedback} onSeek={url ? seek : undefined} />}
            <AnalysisPanel
              video={video}
              analysis={analysis}
              analysisError={analysisError}
              onSeek={url ? seek : undefined}
            />
          </div>
        </details>
        <DeleteVideo id={video.id} stuck={false} />
      </>
    );
  }

  return (
    <>
      {back}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="indigo">Your upload</Badge>
            <Badge tone={statusTone[video.status]}>
              {statusLabel[video.status]}
            </Badge>
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

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          {player}
          {feedback ? (
            <FeedbackPanel
              feedback={feedback}
              onSeek={url ? seek : undefined}
            />
          ) : (
            interpretation && (
              <InterpretationPanel
                interpretation={interpretation}
                onSeek={url ? seek : undefined}
              />
            )
          )}
          <AnalysisPanel
            video={video}
            analysis={analysis}
            analysisError={analysisError}
            onSeek={url ? seek : undefined}
          />
          <p className="text-sm text-slate-600">
            Drills and training plans aren&apos;t available yet.{" "}
            <Link
              href="/feedback/a-1042"
              className="inline-flex items-center gap-0.5 font-medium text-sky-700 hover:text-sky-900"
            >
              See an example of what they will look like{" "}
              <ChevronIcon className="h-4 w-4" />
            </Link>
          </p>
        </div>
        <div className="lg:col-span-2">
          <SessionCard video={video} />
          <DeleteVideo id={video.id} stuck={video.status === "deleting"} />
        </div>
      </div>
    </>
  );
}

// Deleting is permanent, so it takes two deliberate steps and says exactly what goes.
function DeleteVideo({ id, stuck }: { id: string; stuck: boolean }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setError(null);
    const res = await deleteVideo(id);
    if (res.ok) router.replace("/history");
    else {
      setError(res.error);
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 rounded-2xl border border-slate-200 p-4">
      <p className="text-sm font-medium text-slate-900">Delete this video</p>
      {stuck ? (
        <p className="mt-1 text-sm text-slate-600">
          Deleting this video was started but did not finish. Nothing new is
          being added to it.
        </p>
      ) : (
        <p className="mt-1 text-sm text-slate-600">
          Removes the video file, its analysis and pose data, and the feedback
          made from it. This can&apos;t be undone.
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {confirming || stuck ? (
        <div
          className="mt-3 flex flex-wrap gap-2"
          role="group"
          aria-label="Confirm deletion"
        >
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            className="rounded-lg bg-red-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-800 focus-visible:ring-4 focus-visible:ring-red-600/30 focus-visible:outline-none disabled:opacity-60"
          >
            {busy
              ? "Deleting…"
              : stuck
                ? "Finish deleting"
                : "Yes, delete it permanently"}
          </button>
          {!stuck && (
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={busy}
              className="rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100"
            >
              Keep it
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="mt-3 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          Delete video…
        </button>
      )}
    </div>
  );
}

function SessionCard({ video }: { video: VideoRecord }) {
  const rows: [string, string | undefined][] = [
    ["Stroke", video.stroke],
    ["Filming angle", video.camera],
    ["Distance in clip", video.distance || undefined],
    ["Pool length", video.poolLength],
    [
      "Time",
      video.timeSeconds !== undefined
        ? formatSwimTime(video.timeSeconds)
        : undefined,
    ],
    [
      "Swim date",
      video.sessionDate
        ? new Date(`${video.sessionDate}T00:00:00`).toLocaleDateString(
            "en-US",
            {
              month: "short",
              day: "numeric",
              year: "numeric",
            },
          )
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
