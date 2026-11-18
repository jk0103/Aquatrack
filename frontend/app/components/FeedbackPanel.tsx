"use client";

import Link from "next/link";

import { Badge, Card } from "@/app/components/ui";
import { formatMetric, unitLabel } from "@/app/lib/analysisV1";
import type { Feedback, FeedbackItem } from "@/app/lib/feedback";
import { followUpLabel } from "@/app/lib/history";

// Feedback for one swim. Each part has its own card and its own label, so a measurement is
// never read as a problem and general information is never read as something found in the
// swimmer's video. Empty parts say why they are empty; nothing is filled in with advice.
export function FeedbackPanel({
  feedback: f,
  onSeek,
}: {
  feedback: Feedback;
  onSeek?: (seconds: number) => void;
}) {
  const of = (category: FeedbackItem["category"]) =>
    f.items.filter((i) => i.category === category);
  const priorities = of("priority");
  const focus = of("focus");
  const observations = of("observation");
  const education = of("education");
  const insufficient = of("insufficient");
  const reference = of("reference");
  return (
    <div className="space-y-6">
      <Card title="Improvement priorities">
        {priorities.length > 0 ? (
          <ol className="divide-y divide-slate-100">
            {priorities.map((item) => (
              <Item key={item.id} item={item} onSeek={onSeek} />
            ))}
          </ol>
        ) : (
          <p className="text-sm text-slate-600">
            No priorities from this video.{" "}
            {focus.length > 0
              ? "Something below may deserve a look, but one clip is not enough to rank it: that takes the same pattern in another comparable swim, or a goal on your profile that it matches."
              : "Its measurements don't support any. That is a normal result: a priority is only given when the evidence is there."}
          </p>
        )}
      </Card>

      <Card title="What may deserve attention">
        {focus.length > 0 ? (
          <>
            <p className="mb-4 text-sm text-slate-600">
              Patterns in your own swimming that are worth a look. They are not
              confirmed faults.
            </p>
            <ul className="divide-y divide-slate-100">
              {focus.map((item) => (
                <Item key={item.id} item={item} onSeek={onSeek} />
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-slate-600">
            {priorities.length > 0
              ? "Nothing beyond the priorities above."
              : "Nothing in this video's measurements is strong enough to point at."}
          </p>
        )}
      </Card>

      <p className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
        {priorities.length + focus.length > 0
          ? "Practice linked to what is listed above is on your Training page, marked Analysis-based where this analysis supports it."
          : "This video gives no reason to correct anything. Your Training page can still plan practice from your goals, and labels it Goal-based."}{" "}
        <Link href="/training" className="font-medium text-sky-700 hover:text-sky-900">
          Open Training
        </Link>
      </p>

      <Card title="Measured in your video">
        {observations.length > 0 ? (
          <>
            <p className="mb-4 text-sm text-slate-600">
              What the video shows, as measurements. Nothing here is compared
              with other swimmers or with an ideal stroke.
            </p>
            <ul className="divide-y divide-slate-100">
              {observations.map((item) => (
                <Item key={item.id} item={item} onSeek={onSeek} />
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-slate-600">
            Nothing could be measured reliably in this video. See &ldquo;What we
            could not determine&rdquo; and the filming tips below.
          </p>
        )}
      </Card>

      {f.followups.length > 0 && (
        <Card title="Checkpoints from your previous video">
          <p className="mb-4 text-sm text-slate-600">
            What this video says about the checkpoints set after your previous
            one. A change means a number moved by more than the measurement can
            account for. It is not called an improvement here.
          </p>
          <ul className="space-y-3">
            {f.followups.map((u) => (
              <li key={u.checkpointId} className="text-sm">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium text-slate-900">{u.title}</span>
                  <Badge tone="slate">{followUpLabel[u.state]}</Badge>
                </div>
                <p className="mt-0.5 text-slate-600">{u.explanation}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {f.checkpoints.length > 0 && (
        <Card title="For your next video">
          <p className="mb-4 text-sm text-slate-600">
            What to film and what to look for next time. These are checkpoints,
            not a training plan, and one session is not expected to change them.
          </p>
          <ul className="space-y-4">
            {f.checkpoints.map((c) => (
              <li key={c.id}>
                <p className="text-sm font-medium text-slate-900">{c.title}</p>
                <p className="mt-1 text-sm text-slate-600">{c.whatToFilm}</p>
                <dl className="mt-1.5 space-y-1 text-xs text-slate-500">
                  {c.minimum && (
                    <div>
                      <dt className="inline font-medium text-slate-700">
                        How much:{" "}
                      </dt>
                      <dd className="inline">{c.minimum}</dd>
                    </div>
                  )}
                  {c.compareWith && (
                    <div>
                      <dt className="inline font-medium text-slate-700">
                        Compare with:{" "}
                      </dt>
                      <dd className="inline">{c.compareWith}</dd>
                    </div>
                  )}
                  {c.whatCountsAsAChange && (
                    <div>
                      <dt className="inline font-medium text-slate-700">
                        What counts as a change:{" "}
                      </dt>
                      <dd className="inline">{c.whatCountsAsAChange}</dd>
                    </div>
                  )}
                  {c.limitations.map((text) => (
                    <div key={text}>
                      <dd>{text}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {reference.length > 0 && (
        <Card title="Compared with strong swimmers">
          <p className="mb-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
            <span className="font-medium text-slate-900">
              For orientation only.
            </span>{" "}
            The same measurements on a few strong swimmers filmed the same way.
            Good swimmers differ from each other, so a value outside their range
            only says where yours sits.
          </p>
          <ul className="divide-y divide-slate-100">
            {reference.map((item) => (
              <Item key={item.id} item={item} />
            ))}
          </ul>
        </Card>
      )}

      {education.length > 0 && (
        <Card title="General information for your goals">
          <p className="mb-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
            <span className="font-medium text-slate-900">
              Not about your video.
            </span>{" "}
            You chose these goals on your profile, so here is what research says
            about them in general and what this app can and cannot look at. None
            of it is a finding about your swimming.
          </p>
          <ul className="divide-y divide-slate-100">
            {education.map((item) => (
              <Item key={item.id} item={item} />
            ))}
          </ul>
        </Card>
      )}

      <Card title="What we could not determine">
        <p className="mb-3 text-sm text-slate-600">
          Limits of this video and of what can be concluded from it. None of
          these says anything about how well you swim.
        </p>
        <ul className="space-y-2.5">
          {insufficient.map((item) => (
            <li key={item.id} className="text-sm">
              <span className="font-medium text-slate-900">{item.title}</span>
              <span className="text-slate-600"> · {item.text}</span>
            </li>
          ))}
        </ul>
        {f.recordingTips.length > 0 && (
          <div className="mt-4 rounded-xl bg-slate-50 p-3">
            <p className="mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">
              Filming tips for a video that can be analyzed
            </p>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
              {f.recordingTips.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {f.references.length > 0 && (
        <Card title="Research referred to">
          <p className="mb-3 text-sm text-slate-600">
            Checked against the published record; only the abstracts were read.
            Most of these studied competitive adult swimmers, so they describe
            swimming in general, not you.
          </p>
          <ul className="space-y-2.5 text-sm text-slate-600">
            {f.references.map((r) => (
              <li key={r.sourceId}>
                {r.citation}{" "}
                {r.url && (
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-sky-700 hover:text-sky-900"
                  >
                    Open the paper
                  </a>
                )}
                <span className="block text-xs text-slate-500">
                  Studied: {r.population}.
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <p className="text-xs text-slate-500">
        {f.explanationSource === "llm"
          ? "Wording by an AI model from the measured results above; every number and reference was checked against them. No person reviewed this video."
          : "Generated from the measured results. No person reviewed this video."}{" "}
        Feedback v{f.feedbackVersion} · evidence {f.evidenceVersion}
      </p>
    </div>
  );
}

const badge = {
  measured: ["teal", "Measured"],
  for_information: ["slate", "For information only"],
  general: ["indigo", "General information"],
  none: ["slate", ""],
} as const;

function Item({
  item,
  onSeek,
}: {
  item: FeedbackItem;
  onSeek?: (s: number) => void;
}) {
  // Moments to jump to: from the first piece of evidence that has any, so values of
  // different units are never mixed in one row.
  const source = item.evidence.find((e) => e.samples.length > 0);
  const moments = source?.samples ?? [];
  const unit = source ? (unitLabel[source.unit] ?? source.unit) : "";
  const [tone, label] =
    item.category === "priority" || item.category === "focus"
      ? (["amber", "Worth a look"] as const)
      : badge[item.confidence];
  return (
    <li className="py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-slate-900">
          {item.rank !== null ? `${item.rank}. ` : ""}
          {item.title}
        </h3>
        {label && <Badge tone={tone}>{label}</Badge>}
      </div>
      <p className="mt-1 text-sm text-slate-600">{item.text}</p>
      {item.whyItMayMatter && (
        <p className="mt-2 text-sm text-slate-600">
          <span className="font-medium text-slate-900">
            Why it may matter.{" "}
          </span>
          {item.whyItMayMatter}
        </p>
      )}
      {item.monitor && (
        <p className="mt-2 text-sm text-slate-600">
          <span className="font-medium text-slate-900">What to watch. </span>
          {item.monitor}
        </p>
      )}
      {item.factors.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-slate-600">
          {item.factors.map((x) => (
            <li key={x.name}>
              <span className="font-medium text-slate-900 tabular-nums">
                +{x.points}
              </span>{" "}
              {x.name}: {x.detail}
            </li>
          ))}
        </ul>
      )}
      {source && moments.length > 0 && moments.length <= 12 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {moments.map((s) => (
            <li key={`${s.t}-${s.label}`}>
              <button
                type="button"
                onClick={() => onSeek?.(s.t)}
                disabled={!onSeek}
                aria-label={`${source.label}: ${formatMetric(s.value, source.unit)} ${unit} at ${s.t.toFixed(1)} seconds. Show in the video.`}
                className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700 tabular-nums transition hover:bg-sky-100 hover:text-sky-900 focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:outline-none disabled:hover:bg-slate-100"
              >
                {formatMetric(s.value, source.unit)}
                {unit === "°" ? unit : ` ${unit}`} · {s.t.toFixed(1)} s
              </button>
            </li>
          ))}
        </ul>
      )}
      {item.limitations.length > 0 && (
        <details className="mt-2 text-sm text-slate-600">
          <summary className="cursor-pointer text-xs font-medium text-sky-700 hover:text-sky-900">
            Limits, and what this does not say
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-500">
            {item.limitations.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}
