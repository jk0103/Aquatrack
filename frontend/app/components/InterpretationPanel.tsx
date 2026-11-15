"use client";

import { Badge, Card } from "@/app/components/ui";
import { formatMetric, unitLabel } from "@/app/lib/analysisV1";
import type { Finding, Interpretation } from "@/app/lib/interpretation";

// What the measurements of this swim support saying. Four separate parts, so an
// observation is never read as a problem and a missing measurement is never read as
// a fault in the swimmer's technique. Empty parts stay empty: no filler advice.
export function InterpretationPanel({
  interpretation: i,
  onSeek,
}: {
  interpretation: Interpretation;
  onSeek?: (seconds: number) => void;
}) {
  return (
    <div className="space-y-6">
      <Card title="What we observed">
        <p className="mb-4 text-sm text-slate-600">
          {i.baseline
            ? "This is a baseline: there is no earlier swim that can be compared with this one, so these describe this clip on its own."
            : "Described from this clip and compared with your own earlier comparable swims."}{" "}
          These are measurements, not judgements. Nothing is compared with other
          swimmers or with an ideal stroke.
        </p>
        {i.observations.length > 0 ? (
          <ul className="divide-y divide-slate-100">
            {i.observations.map((f) => (
              <FindingRow key={f.id} finding={f} onSeek={onSeek} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-600">
            Nothing could be observed reliably in this clip. The reasons are
            listed under &ldquo;What we could not determine&rdquo;.
          </p>
        )}
      </Card>

      <Card title="What may need attention">
        {i.issueCandidates.length > 0 ? (
          <>
            <p className="mb-4 text-sm text-slate-600">
              Patterns in your own swimming with enough evidence to be worth a
              look. They are not faults measured against a standard.
            </p>
            <ul className="divide-y divide-slate-100">
              {i.issueCandidates.map((f) => (
                <FindingRow key={f.id} finding={f} onSeek={onSeek} />
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-slate-600">
            Nothing in this clip&apos;s measurements is strong enough to say
            that something needs attention. That is a normal result, not a sign
            that the analysis failed.
          </p>
        )}
      </Card>

      <Card title="Improvement priorities">
        {i.priorities.length > 0 && (
          <ol className="mb-3 space-y-4">
            {i.priorities.map((p) => (
              <li key={p.findingId}>
                <p className="text-sm font-medium text-slate-900">
                  {p.rank}. {p.title}
                </p>
                <ul className="mt-1.5 space-y-1 text-xs text-slate-600">
                  {p.factors.map((x) => (
                    <li key={x.name}>
                      <span className="font-medium text-slate-900 tabular-nums">
                        +{x.points}
                      </span>{" "}
                      {x.name}: {x.detail}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        )}
        <p className="text-sm text-slate-600">{i.prioritiesNote}</p>
      </Card>

      <Card title="What we could not determine">
        <p className="mb-3 text-sm text-slate-600">
          Limits of this video and of what can be concluded from it. None of
          these says anything about how well you swim.
        </p>
        <ul className="space-y-2.5">
          {i.undetermined.map((u) => (
            <li key={u.key} className="text-sm">
              <span className="font-medium text-slate-900">{u.title}</span>
              <span className="text-slate-600"> · {u.reason}</span>
            </li>
          ))}
        </ul>
        {i.rules.some((r) => r.state === "pending_validation") && (
          <details className="mt-4 text-sm text-slate-600">
            <summary className="cursor-pointer text-xs font-medium text-sky-700 hover:text-sky-900">
              Judgements we do not make yet, and what they would need
            </summary>
            <ul className="mt-2 space-y-1.5 text-xs">
              {i.rules
                .filter((r) => r.state === "pending_validation")
                .map((r) => (
                  <li key={r.ruleId}>
                    <span className="font-medium text-slate-900">
                      {r.title}.
                    </span>{" "}
                    {r.reason}
                  </li>
                ))}
            </ul>
          </details>
        )}
        <p className="mt-4 text-xs text-slate-500">
          Interpretation v{i.interpretationVersion} · rules {i.rulesVersion}
        </p>
      </Card>
    </div>
  );
}

function FindingRow({
  finding: f,
  onSeek,
}: {
  finding: Finding;
  onSeek?: (s: number) => void;
}) {
  // Moments to jump to: from the first piece of evidence that has any, so values of
  // different units (cycles per minute and seconds, say) are never mixed in one row.
  const source = f.evidence.find((e) => e.samples.length > 0);
  const moments = (source?.samples ?? []).map((s) => ({
    ...s,
    unit: source?.unit ?? "",
    label: source?.label ?? "",
  }));
  return (
    <li className="py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-slate-900">{f.title}</h3>
        {f.evidenceClass === "context_only" ? (
          <Badge tone="slate">For information only</Badge>
        ) : f.level === "issue_candidate" ? (
          <Badge tone="amber">Worth a look</Badge>
        ) : (
          <Badge tone="teal">Measured</Badge>
        )}
      </div>
      <p className="mt-1 text-sm text-slate-600">{f.description}</p>
      {f.contextUsed.length > 0 && (
        <p className="mt-1 text-xs text-slate-500">
          Relates to your goal: {f.contextUsed.join(", ")}.
        </p>
      )}
      {moments.length > 0 && moments.length <= 12 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {moments.map((s) => (
            <li key={`${s.label}-${s.t}`}>
              <button
                type="button"
                onClick={() => onSeek?.(s.t)}
                disabled={!onSeek}
                aria-label={`${s.label}: ${formatMetric(s.value, s.unit)} ${unitLabel[s.unit] ?? s.unit} at ${s.t.toFixed(1)} seconds. Show in the video.`}
                className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 tabular-nums transition hover:bg-sky-100 hover:text-sky-900 focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:outline-none disabled:hover:bg-slate-100"
              >
                {formatMetric(s.value, s.unit)} {unitLabel[s.unit] ?? s.unit} ·{" "}
                {s.t.toFixed(1)} s
              </button>
            </li>
          ))}
        </ul>
      )}
      <details className="mt-2 text-sm text-slate-600">
        <summary className="cursor-pointer text-xs font-medium text-sky-700 hover:text-sky-900">
          Limits, and what this does not say
        </summary>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-500">
          {[...f.limitations, ...f.withheld].map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </details>
    </li>
  );
}
