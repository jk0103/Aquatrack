"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import {
  Badge,
  ButtonLink,
  Card,
  LoadingState,
  PageHeader,
} from "@/app/components/ui";
import {
  formatMetric,
  gradeLabel,
  unitLabel,
  type QualityGrade,
} from "@/app/lib/analysisV1";
import {
  shortDate,
  stateLabel,
  stateTone,
  type SessionComparison,
  type SessionSummary,
} from "@/app/lib/history";
import { fetchComparison } from "@/app/lib/historyApi";

// Two of the swimmer's own videos side by side. The earlier one is always on the left.
// A number that moved is reported as moved; nothing here says better or worse.
export default function ComparePage() {
  return (
    <Suspense fallback={<LoadingState label="Loading…" />}>
      <Compare />
    </Suspense>
  );
}

function Compare() {
  const params = useSearchParams();
  const a = params.get("a");
  const b = params.get("b");
  const [state, setState] = useState<{
    key: string;
    data?: SessionComparison | null;
    error?: string;
  } | null>(null);
  const key = `${a}|${b}`;

  useEffect(() => {
    if (!a || !b) return;
    let live = true;
    fetchComparison(a, b).then((res) => {
      if (live)
        setState(res.ok ? { key, data: res.data } : { key, error: res.error });
    });
    return () => {
      live = false;
    };
  }, [a, b, key]);
  const current = state && state.key === key ? state : null;

  return (
    <>
      <PageHeader
        title="Compare two videos"
        action={<ButtonLink href="/history">Back to history</ButtonLink>}
      />
      {!a || !b ? (
        <Card>
          <p className="text-sm text-slate-600">
            Choose two analyzed videos on the History page to compare them.
          </p>
        </Card>
      ) : current?.error ? (
        <Card>
          <p role="alert" className="text-sm text-red-700">
            Couldn&apos;t compare these videos. {current.error}
          </p>
        </Card>
      ) : !current ? (
        <LoadingState label="Comparing…" />
      ) : !current.data ? (
        <Card>
          <p className="text-sm text-slate-600">
            The comparison is in a format this page can&apos;t show.
          </p>
        </Card>
      ) : (
        <Result c={current.data} />
      )}
    </>
  );
}

function Result({ c }: { c: SessionComparison }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <SessionCard title="Earlier" s={c.previous} />
        <SessionCard title="Later" s={c.current} />
      </div>

      <Card title="What changed">
        <p className="mb-4 text-sm text-slate-600">{c.summary}</p>
        {c.sessionReasons.length === 0 && (
          <ul className="divide-y divide-slate-100">
            {c.metrics.map((m) => {
              const unit = unitLabel[m.unit] ?? m.unit;
              const value = (v: number | null) =>
                v === null
                  ? "not measured"
                  : `${formatMetric(v, m.unit)}${unit === "°" ? unit : ` ${unit}`}`;
              return (
                <li key={m.metricKey} className="py-4 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <h3 className="text-sm font-medium text-slate-900">
                      {m.label}
                    </h3>
                    <Badge tone={stateTone[m.state]}>
                      {stateLabel[m.state]}
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-600 tabular-nums">
                    {value(m.previous)} then, {value(m.current)} now
                    {m.change !== null
                      ? `: a difference of ${formatMetric(m.change, m.unit)}${unit === "°" ? unit : ` ${unit}`}${m.relativePct !== null ? ` (${m.relativePct > 0 ? "+" : ""}${m.relativePct.toFixed(1)}%)` : ""}.`
                      : "."}
                  </p>
                  {m.threshold !== null && (
                    <p className="mt-0.5 text-xs text-slate-500">
                      Differences under {formatMetric(m.threshold, m.unit)}
                      {unit === "°" ? unit : ` ${unit}`} can&apos;t be told from
                      measurement noise.
                    </p>
                  )}
                  {m.reasons.map((text) => (
                    <p key={text} className="mt-1 text-sm text-slate-600">
                      {text}
                    </p>
                  ))}
                </li>
              );
            })}
          </ul>
        )}
        <p className="mt-4 text-xs text-slate-500">
          &ldquo;Increased&rdquo; and &ldquo;decreased&rdquo; say which way a
          number moved. They don&apos;t say whether it is better, or why it
          moved.
        </p>
      </Card>
    </div>
  );
}

const isGrade = (g: string): g is QualityGrade =>
  g === "good" || g === "limited" || g === "insufficient";

function SessionCard({ title, s }: { title: string; s: SessionSummary }) {
  const rows: [string, string][] = [
    ["Date", shortDate(s.recordedAt) || "Not recorded"],
    ["Stroke", s.stroke || "Not given"],
    ["Distance", s.distance || "Not given"],
    ["Pool length", s.poolLength || "Not given"],
    ["Filming angle", s.camera || "Not given"],
    [
      "Following the swimmer",
      isGrade(s.trackingGrade) ? gradeLabel[s.trackingGrade] : "Not recorded",
    ],
    [
      "Camera view",
      s.viewStatus === "changing"
        ? "Changed during the clip"
        : s.viewStatus === "steady"
          ? "Steady"
          : "Can't tell",
    ],
    [
      "Stroke rate",
      s.strokeRate !== null
        ? `${s.strokeRate.toFixed(1)} cycles/min`
        : "Not measured",
    ],
  ];
  return (
    <Card title={title}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="text-slate-900">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-sm">
        <Link
          href={`/history/${s.videoId}`}
          className="font-medium text-sky-700 hover:text-sky-900"
        >
          Open this video and its analysis
        </Link>
      </p>
    </Card>
  );
}
