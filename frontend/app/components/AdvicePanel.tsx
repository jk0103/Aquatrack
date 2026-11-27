"use client";

import type { ReactNode } from "react";

import { Badge, Card } from "@/app/components/ui";
import {
  categoryLabel,
  evidenceLabel,
  type Advice,
  type AdviceStatement,
  type AdviceSuggestion,
} from "@/app/lib/advice";

// The coaching part of a result. Three things are kept visibly apart:
//   - what was measured (observations, what looks consistent)
//   - AI coaching suggestions: ideas to try, never confirmed faults
//   - general practice that does not depend on anything found in the video
// Everything here was stored by the backend when the video was analysed; nothing on this
// panel calls a model.
export function AdvicePanel({
  advice,
  onSeek,
}: {
  advice: Advice;
  onSeek?: (seconds: number) => void;
}) {
  const ai = advice.source === "ai";
  return (
    <div className="space-y-6">
      {/* How to read the result: the three kinds of content never mean the same thing. */}
      <ul className="grid gap-3 rounded-2xl glass p-4 text-sm sm:grid-cols-3 sm:p-5">
        <li>
          <Badge tone="sky">Measured</Badge>
          <p className="mt-1.5 text-slate-600">Numbers taken from your video. Facts, with their limits.</p>
        </li>
        <li>
          <Badge tone="indigo">AI suggestion</Badge>
          <p className="mt-1.5 text-slate-600">
            An AI model&apos;s reading of those numbers: ideas to try, not a diagnosis.
          </p>
        </li>
        <li>
          <Badge tone="teal">General practice</Badge>
          <p className="mt-1.5 text-slate-600">Good freestyle practice for anyone. Not about your video.</p>
        </li>
      </ul>
      <Card
        title="Coaching suggestions"
        action={ai ? <Badge tone="indigo">AI suggestions</Badge> : undefined}
      >
        {ai && advice.suggestions.length > 0 ? (
          <>
            <p className="mb-5 text-sm text-slate-600">
              Ideas to try, worked out by an AI model from the measurements of
              this video. They are suggestions, not confirmed technique faults,
              and no coach has watched this swim.
            </p>
            <ol className="space-y-5">
              {advice.suggestions.map((s, n) => (
                <Suggestion key={s.id} s={s} n={n + 1} onSeek={onSeek} />
              ))}
            </ol>
          </>
        ) : ai ? (
          <p className="text-sm text-slate-600">
            The AI model read your movement and found no repeated pattern worth
            changing. That is a good result, not a missing one. What you
            repeated well and some general practice are below.
          </p>
        ) : (
          <p className="text-sm text-slate-600">
            AI coaching suggestions weren&apos;t made for this video
            {reasonText(advice.fallbackReason)}. The measured feedback and the
            general practice below don&apos;t depend on them.
          </p>
        )}
      </Card>

      {advice.consistent.length > 0 && (
        <Card title="What looks consistent" action={<Badge tone="sky">Measured</Badge>}>
          <p className="mb-3 text-sm text-slate-600">
            Things you repeated well in this video. Nothing here needs fixing.
          </p>
          <Statements items={advice.consistent} tone="teal" onSeek={onSeek} />
        </Card>
      )}

      {advice.generalPractice.length > 0 && (
        <Card title="General practice" action={<Badge tone="teal">Not about your video</Badge>}>
          <p className="mb-4 text-sm text-slate-600">
            Useful freestyle practice from the AquaTrack library. It is not
            based on a problem found in your video.
          </p>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {advice.generalPractice.map((p) => (
              <li key={p.activityId} className="rounded-xl bg-white/60 p-4 ring-1 ring-slate-200">
                <p className="font-medium text-slate-900">{p.name}</p>
                <p className="mt-1 text-sm text-slate-600">{p.purpose}</p>
                {p.instructions.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                    {p.instructions.slice(0, 3).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {(advice.observations.length > 0 ||
        advice.dataQuality.length > 0 ||
        advice.limitations.length > 0) && (
        <details className="group rounded-2xl glass p-5 sm:p-6">
          <summary className="cursor-pointer text-sm font-semibold text-slate-900">
            What the suggestions are based on, and their limits
          </summary>
          <div className="mt-5 space-y-5">
            {advice.observations.length > 0 && (
              <Block title="Measured in your movement">
                <Statements items={advice.observations} tone="sky" onSeek={onSeek} />
              </Block>
            )}
            {advice.dataQuality.length > 0 && (
              <Block title="Where the tracking was unsure">
                <Plain items={advice.dataQuality} />
              </Block>
            )}
            {advice.limitations.length > 0 && (
              <Block title="Limits">
                <Plain items={advice.limitations} />
              </Block>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

function reasonText(reason: string): string {
  if (reason.includes("not enabled")) return " (AI advice is switched off)";
  if (reason.includes("no stroke cycle")) return " (no stroke cycle could be measured)";
  if (reason) return " (the AI step did not produce a usable answer)";
  return "";
}

function Suggestion({
  s,
  n,
  onSeek,
}: {
  s: AdviceSuggestion;
  n: number;
  onSeek?: (seconds: number) => void;
}) {
  return (
    <li className="rounded-xl bg-white/60 p-4 ring-1 ring-slate-200 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">
          {n}
        </span>
        <h3 className="text-base font-semibold text-slate-900">{s.title}</h3>
        <Badge tone="slate">{categoryLabel(s.category)}</Badge>
        {s.evidenceBasis === "exploratory" ? (
          <Badge tone="amber">Exploratory · not a verified measurement</Badge>
        ) : (
          s.tentative && <Badge tone="amber">Tentative</Badge>
        )}
      </div>
      {s.tentative && s.tentativeReasons.length > 0 && (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {s.tentativeReasons.join(" ")}
        </p>
      )}
      <dl className="mt-4 space-y-3 text-sm">
        <Row label="What AquaTrack noticed">{s.noticed}</Row>
        {s.whyItMayMatter && <Row label="Why it might matter">{s.whyItMayMatter}</Row>}
        {s.tryThis && <Row label="Try this">{s.tryThis}</Row>}
        {(s.drillName || s.drillHow) && (
          <Row label="Drill">
            {s.drillName && <span className="font-medium text-slate-900">{s.drillName}. </span>}
            {s.drillHow}
          </Row>
        )}
        {s.checkNextTime && <Row label="Check in your next video">{s.checkNextTime}</Row>}
      </dl>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {s.cyclesSupporting > 0 && <span>Seen in {s.cyclesSupporting} stroke cycles</span>}
        {s.evidenceRefs.slice(0, 4).map((ref) => (
          <Badge key={ref} tone="slate">
            {evidenceLabel(ref)}
          </Badge>
        ))}
        <Times times={s.timesS} onSeek={onSeek} />
      </div>
    </li>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="sm:grid sm:grid-cols-4 sm:gap-3">
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-slate-800 sm:col-span-3 sm:mt-0">{children}</dd>
    </div>
  );
}

function Times({ times, onSeek }: { times: number[]; onSeek?: (seconds: number) => void }) {
  if (!onSeek || times.length === 0) return null;
  return (
    <>
      {times.slice(0, 4).map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => onSeek(t)}
          className="rounded-full bg-sky-50 px-2 py-0.5 font-medium text-sky-700 ring-1 ring-inset ring-sky-600/20 hover:bg-sky-100"
        >
          {t.toFixed(1)} s
        </button>
      ))}
    </>
  );
}

function Statements({
  items,
  tone,
  onSeek,
}: {
  items: AdviceStatement[];
  tone: "teal" | "sky";
  onSeek?: (seconds: number) => void;
}) {
  const dot = tone === "teal" ? "bg-teal-500" : "bg-sky-500";
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.statement} className="flex items-start gap-2.5 text-sm text-slate-800">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} aria-hidden />
          <span>
            {item.statement}{" "}
            <span className="inline-flex flex-wrap gap-1.5 align-middle text-xs">
              <Times times={item.timesS} onSeek={onSeek} />
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-900">{title}</h3>
      {children}
    </div>
  );
}

function Plain({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-600">
      {items.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}
