import Link from "next/link";
import { notFound } from "next/navigation";

import { ChevronIcon } from "@/app/components/icons";
import { FeedbackStage, StatPills } from "@/app/components/FeedbackStage";
import { Button, Card, ExampleNote } from "@/app/components/ui";
import { analyses, formatDate } from "@/app/lib/mock";

const suggestedPlan = [
  {
    day: "Mon",
    set: "Warm-up 400 m, catch-up freestyle 4 × 50 m, pull 4 × 100 m at shoulder-width entry",
  },
  { day: "Wed", set: "Side-kick 6-3-6 drill 4 × 25 m, 8 × 50 m breathing every 3" },
  { day: "Fri", set: "Race pace 4 × 100 m, focus on straight entry when tired" },
];

export default async function FeedbackPage(props: PageProps<"/feedback/[id]">) {
  const { id } = await props.params;
  const analysis = analyses.find((a) => a.id === id);
  if (!analysis) notFound();
  if (analysis.status === "Processing") return <Processing comment={analysis.comment} />;

  return (
    <>
      <nav className="mb-4 text-sm">
        <Link href="/history" className="text-sky-700 hover:text-sky-900">
          History
        </Link>
        <span className="mx-2 text-slate-500">/</span>
        <span className="text-slate-500">{formatDate(analysis.date, { year: "numeric" })}</span>
      </nav>

      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            {analysis.headline}
          </h1>
          <p className="mt-1.5 text-slate-600">
            {formatDate(analysis.date, { weekday: "long", year: "numeric" })} · {analysis.stroke}{" "}
            {analysis.distance} · {analysis.camera}
          </p>
        </div>
      </div>

      <div className="mb-4">
        <ExampleNote>
          This is an example analysis showing what your feedback will look like.
        </ExampleNote>
      </div>

      <div className="mb-5">
        <StatPills analysis={analysis} />
      </div>

      <FeedbackStage
        analysis={analysis}
        aside={
          <Card title="Suggested training plan">
            <p className="mb-4 text-sm text-slate-600">
              One week built around your main fix. Repeat for 3 weeks, then upload another swim.
            </p>
            <ul className="space-y-3">
              {suggestedPlan.map((d) => (
                <li key={d.day} className="flex gap-3">
                  <span className="flex h-9 w-11 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-xs font-semibold text-sky-700">
                    {d.day}
                  </span>
                  <span className="text-sm text-slate-700">{d.set}</span>
                </li>
              ))}
            </ul>
            <div className="mt-5 flex flex-col gap-2 sm:flex-row">
              <Button className="flex-1">Add to my training</Button>
              <Link
                href="/training"
                className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg px-4 py-2.5 text-sm font-semibold text-sky-700 hover:bg-sky-50"
              >
                See my plans <ChevronIcon className="h-4 w-4" />
              </Link>
            </div>
          </Card>
        }
      />
    </>
  );
}

function Processing({ comment }: { comment: string }) {
  return (
    <div className="mx-auto max-w-lg py-10 text-center">
      <div className="relative mx-auto h-20 w-20 overflow-hidden rounded-full bg-sky-100">
        <div className="absolute inset-x-0 bottom-0 h-1/2 animate-pulse bg-gradient-to-t from-sky-500 to-cyan-300" />
      </div>
      <h1 className="mt-6 text-2xl font-semibold tracking-tight text-slate-900">
        Analyzing your swim
      </h1>
      <p className="mt-2 text-slate-600">
        We&apos;re tracking your body position frame by frame. Your feedback will show up in History
        when it&apos;s ready.
      </p>
      {comment && <p className="mt-4 text-sm text-slate-500">Your note: “{comment}”</p>}
      <Link
        href="/history"
        className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-sky-700 hover:text-sky-900"
      >
        Back to history <ChevronIcon className="h-4 w-4" />
      </Link>
    </div>
  );
}
