"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { FeedbackCard, type ListEntry } from "@/app/components/FeedbackStage";
import { ChevronIcon } from "@/app/components/icons";
import { Badge, Button, Card } from "@/app/components/ui";
import type { Feedback, FeedbackCategory } from "@/app/lib/feedback";
import { basisLabel, basisNote, basisTone, localIso, type TrainingPlan } from "@/app/lib/training";
import { previewPlan, savePlan } from "@/app/lib/trainingApi";

// The part of the example page below the stage (/feedback/a-1042), filled from the real
// feedback and a real plan preview. Same card, tabs, rows and motion as the example.

const GROUP: Record<FeedbackCategory, { group: Group; badge: string; tone: ListEntry["tone"] }> = {
  priority: { group: "Priority", badge: "Priority", tone: "amber" },
  focus: { group: "Focus", badge: "Focus", tone: "sky" },
  // Neutral: a measurement is not good or bad.
  observation: { group: "Measured", badge: "Measured", tone: "slate" },
  education: { group: "General", badge: "General", tone: "indigo" },
  // Strong-swimmer reference hints: orientation only, never a finding.
  reference: { group: "General", badge: "Reference", tone: "indigo" },
  insufficient: { group: "Not measured", badge: "Not measured", tone: "slate" },
};
const ALL_GROUPS = ["All", "Priority", "Focus", "Measured", "General", "Not measured"] as const;
type Group = (typeof ALL_GROUPS)[number];

export function feedbackEntries(f: Feedback): ListEntry<Group>[] {
  return f.items.map((item) => {
    const g = GROUP[item.category];
    return {
      id: item.id,
      group: g.group,
      title: item.title,
      badge: g.badge,
      tone: g.tone,
      detail: item.text,
      lineLabel: item.monitor ? "Next video: " : undefined,
      line: item.monitor || undefined,
    };
  });
}

export function ResultFeedbackCard({ feedback, comment }: { feedback: Feedback; comment?: string }) {
  const entries = feedbackEntries(feedback);
  // Tabs only for groups this feedback has; "All" always.
  const groups = ALL_GROUPS.filter((g) => g === "All" || entries.some((e) => e.group === g));
  return <FeedbackCard groups={groups} entries={entries} comment={comment} />;
}

const weekday = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { weekday: "short" });

function sessionText(s: TrainingPlan["sessions"][number]): string {
  const sets = s.items.map((i) => (i.sets ? `${i.name} ${i.sets}` : i.name)).join(", ");
  return sets ? `${s.title}: ${sets}` : s.title;
}

// The plan the training planner would make this week (a preview: nothing is saved until the
// swimmer adds it). Hidden when the planner can't be reached.
export function SuggestedPlanCard({ videoId }: { videoId: string }) {
  const [plan, setPlan] = useState<TrainingPlan | null | undefined>(undefined);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "conflict">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    previewPlan("week", localIso(new Date())).then((res) => {
      if (live) setPlan(res.ok ? res.data : null);
    });
    return () => {
      live = false;
    };
  }, []);

  if (!plan || !plan.sessions.length) return null;

  async function add() {
    if (!plan) return;
    setState("saving");
    setError(null);
    const res = await savePlan(plan.kind, plan.start_date, plan.token);
    if (!res.ok) {
      setError(res.error);
      return setState("idle");
    }
    setState(res.data.saved ? "saved" : "conflict");
  }

  return (
    <Card title="Suggested training plan" action={<Badge tone={basisTone(plan.basis)}>{basisLabel(plan.basis)}</Badge>}>
      <ul className="space-y-3">
        {plan.sessions.map((s) => (
          <li key={s.id || s.date} className="flex gap-3">
            <span className="flex h-9 w-11 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-xs font-semibold text-sky-700">
              {weekday(s.date)}
            </span>
            <span className="text-sm text-slate-700">{sessionText(s)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-slate-500">
        {basisNote(plan.basis)}
        {plan.inputs.video_id && plan.inputs.video_id !== videoId
          ? " Built from your latest analysed swim."
          : ""}
      </p>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {state === "conflict" && (
        <p className="mt-2 text-sm text-slate-600">
          You already have training planned this week. Choose what to keep on your plans page.
        </p>
      )}
      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        <Button
          className="flex-1"
          onClick={add}
          disabled={state !== "idle"}
        >
          {state === "saving" ? "Adding…" : state === "saved" ? "Added to my training" : "Add to my training"}
        </Button>
        <Link
          href="/training"
          className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg px-4 py-2.5 text-sm font-semibold text-sky-700 hover:bg-sky-50"
        >
          See my plans <ChevronIcon className="h-4 w-4" />
        </Link>
      </div>
    </Card>
  );
}

export function NextVideoCard({ feedback }: { feedback: Feedback }) {
  if (!feedback.checkpoints.length) return null;
  return (
    <Card title="Check in your next video">
      <ul className="space-y-2 text-sm text-slate-700">
        {feedback.checkpoints.map((c) => (
          <li key={c.id} className="flex gap-2">
            <span aria-hidden="true" className="text-teal-600">
              ✓
            </span>
            <span>
              {c.title}
              {c.whatToFilm && <span className="block text-xs text-slate-500">{c.whatToFilm}</span>}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
