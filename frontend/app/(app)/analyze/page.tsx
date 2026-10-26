"use client";

import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import type { UploadTask } from "firebase/storage";

import { useUser } from "@/app/components/AppShell";
import { FormError } from "@/app/components/fields";
import { UploadIcon } from "@/app/components/icons";
import { Button, ButtonLink, Card, LaneProgress, PageHeader } from "@/app/components/ui";
import { describeFirebaseError } from "@/app/lib/firebase";
import { parseSwimTime } from "@/app/lib/profile";
import {
  CAMERAS,
  checkVideoFile,
  DISTANCES,
  formatBytes,
  formatDuration,
  POOL_LENGTHS,
  STROKES,
  SUGGESTED_MAX_SECONDS,
  uploadVideo,
} from "@/app/lib/videos";

const selectClass =
  "block w-full rounded-lg border border-slate-300 bg-surface px-3.5 py-2.5 text-slate-900 shadow-sm focus:border-sky-600 focus:outline-none focus:ring-4 focus:ring-sky-600/15";
const labelClass = "block text-sm font-medium text-slate-700";

function localIsoDay(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function AnalyzePage() {
  const user = useUser();
  const input = useRef<HTMLInputElement>(null);
  const task = useRef<UploadTask | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [camera, setCamera] = useState(CAMERAS[0].value);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Problems with the chosen file show by the drop zone, where the file was chosen.
  const [fileError, setFileError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ id: string; name: string } | null>(null);
  const [today] = useState(() => localIsoDay());
  const uploading = progress !== null;

  // Leaving the page mid-upload stops the upload and frees the preview.
  const previewRef = useRef<string | null>(null);
  useEffect(
    () => () => {
      task.current?.cancel();
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    },
    [],
  );

  // A local link to the chosen file so it can play before it's uploaded.
  function setPreview(next: File | null) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = next ? URL.createObjectURL(next) : null;
    setPreviewUrl(previewRef.current);
  }

  function choose(next: File | undefined | null) {
    if (uploading || !next) return;
    const problem = checkVideoFile(next);
    setFileError(problem);
    setError(null);
    if (problem) return;
    setFile(next);
    setPreview(next);
    setDuration(null);
    setPreviewFailed(false);
  }

  function clearFile() {
    setFile(null);
    setPreview(null);
    setDuration(null);
    setPreviewFailed(false);
    if (input.current) input.current.value = "";
  }

  function onDrag(event: DragEvent, over: boolean) {
    event.preventDefault();
    if (!uploading) setDragging(over);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const files = event.dataTransfer.files;
    if (files.length > 1) return setFileError("Drop one video at a time.");
    choose(files[0]);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (uploading || !user) return;
    if (!file) return setFileError("Choose a video to upload.");
    const problem = checkVideoFile(file);
    if (problem) return setFileError(problem);

    const form = new FormData(event.currentTarget);
    const timeText = String(form.get("time") ?? "").trim();
    const timeSeconds = timeText ? parseSwimTime(timeText) : undefined;
    if (timeSeconds === null)
      return setError("Enter the time like 28.45 or 1:02.30, or leave it blank.");
    if (timeSeconds !== undefined && (timeSeconds < 5 || timeSeconds > 3600)) {
      return setError("That time looks off. Check it or leave it blank.");
    }
    const sessionDate = String(form.get("session_date") ?? "");
    if (sessionDate && sessionDate > today)
      return setError("The swim date can't be in the future.");

    setError(null);
    setProgress(0);
    try {
      const id = await uploadVideo(
        user.uid,
        file,
        {
          stroke: String(form.get("stroke")),
          camera,
          distance: String(form.get("distance")),
          poolLength: String(form.get("pool_length")),
          timeSeconds,
          sessionDate: sessionDate || undefined,
          durationSeconds: duration ? Math.round(duration * 10) / 10 : undefined,
          comments: String(form.get("comments") ?? "").trim(),
          wantFeedback: form.get("want_feedback") === "on",
          wantPlan: form.get("want_plan") === "on",
        },
        setProgress,
        (t) => (task.current = t),
      );
      setSaved({ id, name: file.name });
      clearFile();
    } catch (err) {
      const code = (err as { code?: string })?.code;
      setError(
        code === "storage/canceled"
          ? "Upload cancelled. Your details are still filled in."
          : `${describeFirebaseError(err)} Your details are still filled in, so you can try again.`,
      );
    } finally {
      task.current = null;
      setProgress(null);
    }
  }

  if (saved) {
    return (
      <div className="mx-auto max-w-lg py-10 text-center" role="status">
        <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-teal-100 text-2xl text-teal-700">
          ✓
        </span>
        <h1 className="mt-5 text-2xl font-semibold tracking-tight text-slate-900">
          Video uploaded
        </h1>
        <p className="mt-2 text-slate-600">
          {saved.name} is saved to your history. It hasn&apos;t been analyzed yet: technique
          feedback will appear on its page once analysis is connected.
        </p>
        <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink href={`/history/${saved.id}`}>Watch your video</ButtonLink>
          <Button variant="secondary" onClick={() => setSaved(null)}>
            Upload another
          </Button>
        </div>
      </div>
    );
  }

  const longClip = duration !== null && duration > SUGGESTED_MAX_SECONDS;

  return (
    <>
      <PageHeader
        title="Analyze a swim"
        subtitle="Upload a video and tell us about the swim. It's saved to your history, ready for technique analysis."
      />

      <form onSubmit={onSubmit} className="grid gap-6 lg:grid-cols-5" noValidate>
        <Card className="lg:col-span-3">
          <input
            ref={input}
            id="video"
            type="file"
            accept="video/*,.mp4,.mov,.m4v,.webm"
            className="sr-only"
            disabled={uploading}
            onChange={(e) => choose(e.target.files?.[0])}
          />
          {file && previewUrl ? (
            <div
              onDragEnter={(e) => onDrag(e, true)}
              onDragOver={(e) => onDrag(e, true)}
              onDragLeave={(e) => onDrag(e, false)}
              onDrop={onDrop}
              className={`rounded-xl transition ${dragging ? "ring-4 ring-sky-500/40" : ""}`}
            >
              {previewFailed ? (
                <div className="flex aspect-video flex-col items-center justify-center rounded-xl bg-gradient-to-b from-sky-800 to-cyan-900 px-6 text-center text-sm text-sky-50">
                  <p className="font-semibold">This browser can&apos;t preview this file</p>
                  <p className="mt-1 text-sky-100/80">
                    Some phone videos (HEVC .mov) only play in Safari. You can still upload it.
                  </p>
                </div>
              ) : (
                <video
                  key={previewUrl}
                  src={previewUrl}
                  controls
                  muted
                  playsInline
                  preload="metadata"
                  onLoadedMetadata={(e) =>
                    setDuration(
                      Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : null,
                    )
                  }
                  onError={() => setPreviewFailed(true)}
                  className="aspect-video w-full rounded-xl bg-black object-contain"
                  aria-label={`Preview of ${file.name}`}
                />
              )}
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-900">{file.name}</p>
                  <p className="text-sm text-slate-500">
                    {formatBytes(file.size)}
                    {duration !== null && ` · ${formatDuration(duration)}`}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    disabled={uploading}
                    onClick={() => input.current?.click()}
                  >
                    Replace
                  </Button>
                  <Button variant="secondary" disabled={uploading} onClick={clearFile}>
                    Remove
                  </Button>
                </div>
              </div>
              {longClip && (
                <p className="mt-3 rounded-lg bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
                  This clip is {formatDuration(duration!)} long. Clips under 2 minutes upload faster
                  and are easier to analyze; trimming to one or two lengths is best.
                </p>
              )}
            </div>
          ) : (
            <label
              htmlFor="video"
              onDragEnter={(e) => onDrag(e, true)}
              onDragOver={(e) => onDrag(e, true)}
              onDragLeave={(e) => onDrag(e, false)}
              onDrop={onDrop}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition focus-within:ring-4 focus-within:ring-sky-600/20 ${
                dragging
                  ? "border-sky-600 bg-sky-50 ring-4 ring-sky-500/20"
                  : "border-sky-300 bg-sky-50/60 hover:border-sky-500 hover:bg-sky-50"
              }`}
            >
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-surface text-sky-700 shadow-sm">
                <UploadIcon className="h-6 w-6" />
              </span>
              <span className="mt-4 font-semibold text-slate-900">
                {dragging ? "Drop the video here" : "Choose a video or drag it here"}
              </span>
              <span className="mt-1 text-sm text-slate-500">
                MP4, MOV or WebM, up to 500 MB. Under 2 minutes works best.
              </span>
            </label>
          )}

          {fileError && (
            <div className="mt-3">
              <FormError message={fileError} />
            </div>
          )}

          <fieldset className="mt-6">
            <legend className="mb-2 text-sm font-medium text-slate-700">Filming angle</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {CAMERAS.map((c) => (
                <label
                  key={c.value}
                  className={`cursor-pointer rounded-xl border p-4 transition focus-within:ring-4 focus-within:ring-sky-600/20 ${
                    camera === c.value
                      ? "border-sky-600 bg-sky-50 ring-4 ring-sky-600/10"
                      : "border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <input
                    type="radio"
                    name="camera"
                    value={c.value}
                    checked={camera === c.value}
                    onChange={() => setCamera(c.value)}
                    className="sr-only"
                  />
                  <span className="block font-medium text-slate-900">{c.value}</span>
                  <span className="text-sm text-slate-500">{c.note}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="stroke" className={labelClass}>
                Stroke
              </label>
              <select id="stroke" name="stroke" className={selectClass} defaultValue="Freestyle">
                {STROKES.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="distance" className={labelClass}>
                Distance in clip
              </label>
              <select id="distance" name="distance" className={selectClass} defaultValue="50 m">
                {DISTANCES.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="pool_length" className={labelClass}>
                Pool length
              </label>
              <select
                id="pool_length"
                name="pool_length"
                className={selectClass}
                defaultValue="25 m"
              >
                {POOL_LENGTHS.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="session_date" className={labelClass}>
                Date of the swim
              </label>
              <input
                id="session_date"
                name="session_date"
                type="date"
                defaultValue={today}
                max={today}
                className={selectClass}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <label htmlFor="time" className={labelClass}>
                Time <span className="font-normal text-slate-500">(optional)</span>
              </label>
              <input
                id="time"
                name="time"
                inputMode="decimal"
                autoComplete="off"
                placeholder="e.g. 31.80 or 1:05.20"
                aria-describedby="time-hint"
                className={selectClass}
              />
              <p id="time-hint" className="text-xs text-slate-500">
                Your own timed result for the distance in the clip, if you have one.
              </p>
            </div>
          </div>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card title="Session notes">
            <label htmlFor="comments" className="sr-only">
              Session notes
            </label>
            <textarea
              id="comments"
              name="comments"
              rows={5}
              maxLength={2000}
              placeholder="How did it feel? Anything you want us to look at, like your breathing or the kick on the last length?"
              className={`${selectClass} resize-y`}
            />
          </Card>

          <Card title="What would you like back?">
            <div className="space-y-3">
              {[
                ["want_feedback", "Technique feedback", "Annotated frames and what to fix first"],
                [
                  "want_plan",
                  "Training plan suggestion",
                  "Drills and sets built around the feedback",
                ],
              ].map(([name, label, note]) => (
                <label key={name} className="flex gap-3">
                  <input
                    type="checkbox"
                    name={name}
                    defaultChecked
                    className="mt-1 h-4 w-4 rounded border-slate-300 accent-sky-700"
                  />
                  <span>
                    <span className="block font-medium text-slate-900">{label}</span>
                    <span className="text-sm text-slate-500">{note}</span>
                  </span>
                </label>
              ))}
            </div>
            <p className="mt-4 text-xs text-slate-500">
              Analysis isn&apos;t connected yet. Your video and these choices are saved so it can
              run later.
            </p>
          </Card>

          <FormError message={error} />
          {uploading && (
            <div className="space-y-2" aria-live="polite">
              <LaneProgress value={progress * 100} label="Upload progress" />
              <div className="flex items-center justify-between text-sm text-slate-600">
                <span>Uploading… {Math.round(progress * 100)}%</span>
                <button
                  type="button"
                  onClick={() => task.current?.cancel()}
                  className="tap-target font-medium text-sky-700 hover:text-sky-900"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          <Button type="submit" className="w-full py-3" disabled={uploading || !user}>
            {uploading ? "Uploading…" : file ? "Upload video" : "Choose a video to upload"}
          </Button>
        </div>
      </form>
    </>
  );
}
