"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { UploadIcon } from "@/app/components/icons";
import { Button, Card, PageHeader } from "@/app/components/ui";

const strokes = ["Freestyle", "Backstroke", "Breaststroke", "Butterfly"];
const cameras = [
  { value: "Underwater", note: "Side view below the surface" },
  { value: "Overhead", note: "From the deck or above the pool" },
];

const selectClass =
  "block w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm focus:border-sky-600 focus:outline-none focus:ring-4 focus:ring-sky-600/15";

export default function AnalyzePage() {
  const router = useRouter();
  const [fileName, setFileName] = useState<string | null>(null);
  const [camera, setCamera] = useState("Underwater");

  // Layout only: shows the example feedback instead of uploading.
  function onSubmit(event: FormEvent) {
    event.preventDefault();
    router.push("/feedback/a-1042");
  }

  return (
    <>
      <PageHeader
        title="Analyze a swim"
        subtitle="Upload a video and tell us how it felt. You'll get technique feedback and a suggested training plan."
      />

      <form onSubmit={onSubmit} className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <label
            htmlFor="video"
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-sky-300 bg-sky-50/60 px-6 py-12 text-center transition hover:border-sky-500 hover:bg-sky-50"
          >
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-white text-sky-700 shadow-sm">
              <UploadIcon className="h-6 w-6" />
            </span>
            <span className="mt-4 font-semibold text-slate-900">
              {fileName ?? "Choose a video or drag it here"}
            </span>
            <span className="mt-1 text-sm text-slate-500">
              {fileName ? "Click to choose a different file" : "MP4 or MOV, up to 2 minutes"}
            </span>
            <input
              id="video"
              type="file"
              accept="video/*"
              className="sr-only"
              onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
            />
          </label>

          <fieldset className="mt-6">
            <legend className="mb-2 text-sm font-medium text-slate-700">Camera view</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {cameras.map((c) => (
                <label
                  key={c.value}
                  className={`cursor-pointer rounded-xl border p-4 transition ${
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
              <label htmlFor="stroke" className="block text-sm font-medium text-slate-700">
                Stroke
              </label>
              <select id="stroke" name="stroke" className={selectClass} defaultValue="Freestyle">
                {strokes.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="distance" className="block text-sm font-medium text-slate-700">
                Distance in clip
              </label>
              <select id="distance" name="distance" className={selectClass} defaultValue="50 m">
                {["25 m", "50 m", "100 m", "200 m"].map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </div>
          </div>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card title="Your comments">
            <label htmlFor="comments" className="sr-only">
              Comments
            </label>
            <textarea
              id="comments"
              name="comments"
              rows={5}
              placeholder="How did it feel? Anything you want us to look at, like your breathing or the kick on the last length?"
              className={`${selectClass} resize-y`}
            />
          </Card>

          <Card title="What would you like back?">
            <div className="space-y-3">
              {[
                ["Technique feedback", "Annotated frames and what to fix first"],
                ["Training plan suggestion", "Drills and sets built around the feedback"],
              ].map(([label, note]) => (
                <label key={label} className="flex gap-3">
                  <input
                    type="checkbox"
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
          </Card>

          <Button type="submit" className="w-full py-3">
            Analyze my swim
          </Button>
        </div>
      </form>
    </>
  );
}
