import {
  Badge,
  ButtonLink,
  Card,
  ExampleNote,
  LaneProgress,
  PageHeader,
} from "@/app/components/ui";
import { trainingPlans } from "@/app/lib/mock";

const thisWeek = [
  { day: "Mon", title: "Single-arm fly", distance: "1,200 m", done: true },
  { day: "Tue", title: "Rest", distance: "", done: true },
  { day: "Wed", title: "Catch-up drills", distance: "1,800 m", done: true },
  { day: "Thu", title: "Aerobic base", distance: "3,000 m", done: false, today: true },
  { day: "Fri", title: "Broken 100s", distance: "2,400 m", done: false },
  { day: "Sat", title: "Rest", distance: "", done: false },
  { day: "Sun", title: "Fall Invitational", distance: "Meet", done: false },
];

export default function TrainingPage() {
  return (
    <>
      <PageHeader
        title="Training"
        subtitle="Plans you're working through, built from your feedback."
        action={<ButtonLink href="/analyze">Get a new plan</ButtonLink>}
      />
      <div className="mb-6">
        <ExampleNote>
          These training plans are examples. Your own plans will appear here once your swims are
          analyzed.
        </ExampleNote>
      </div>

      <Card title="This week" className="mb-6">
        <ol className="grid grid-cols-7 gap-1.5 sm:gap-3">
          {thisWeek.map((d) => (
            <li
              key={d.day}
              className={`flex flex-col items-center rounded-xl px-1 py-3 text-center sm:px-2 ${
                d.today ? "bg-sky-700 text-white" : d.done ? "bg-sky-50" : "bg-slate-50"
              }`}
            >
              <span
                className={`text-xs font-semibold ${d.today ? "text-sky-100" : "text-slate-500"}`}
              >
                {d.day}
              </span>
              <span
                className={`mt-2 flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                  d.done
                    ? "bg-teal-500 text-white"
                    : d.today
                      ? "border-2 border-white"
                      : "border-2 border-slate-300"
                }`}
              >
                {d.done ? "✓" : ""}
              </span>
              <span className="mt-2 hidden text-xs font-medium sm:block">{d.title}</span>
              {d.distance && (
                <span
                  className={`hidden text-[11px] sm:block ${d.today ? "text-sky-100" : "text-slate-500"}`}
                >
                  {d.distance}
                </span>
              )}
            </li>
          ))}
        </ol>
        <p className="mt-4 text-sm text-slate-600 sm:hidden">
          Today: <span className="font-medium text-slate-900">Aerobic base, 3,000 m</span>
        </p>
      </Card>

      <h2 className="mb-4 font-semibold text-slate-900">In progress</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {trainingPlans.map((plan) => (
          <Card key={plan.id} className="flex flex-col">
            <div className="mb-3 flex items-center justify-between gap-2">
              <Badge>
                Week {plan.week} of {plan.weeks}
              </Badge>
              <span className="text-sm text-slate-500">
                {plan.done}/{plan.total} sessions
              </span>
            </div>
            <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
            <p className="mt-1 text-sm text-slate-600">{plan.focus}</p>
            <div className="mt-4">
              <LaneProgress
                value={(plan.done / plan.total) * 100}
                label={`${plan.name} progress`}
              />
            </div>
            <div className="mt-5 flex-1 rounded-xl bg-slate-50 p-3 text-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Next session
              </p>
              <p className="mt-1 text-slate-800">{plan.next}</p>
            </div>
            <button
              type="button"
              disabled
              title="Tracking sessions isn't available yet"
              className="mt-4 cursor-not-allowed rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 opacity-60"
            >
              Mark session done (soon)
            </button>
          </Card>
        ))}
      </div>
    </>
  );
}
