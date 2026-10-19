"use client";

import { useRouter } from "next/navigation";
import { onAuthStateChanged, type User } from "firebase/auth";
import { useEffect, useState, type FormEvent } from "react";

import { FormError } from "@/app/components/fields";
import { Logo } from "@/app/components/Logo";
import { BodyFields, LevelField, PbFields, TrainingFields } from "@/app/components/ProfileFields";
import { auth, describeFirebaseError } from "@/app/lib/firebase";
import {
  BODY_CHECKS,
  checkDraft,
  checkLevel,
  checkPbs,
  emptyDraft,
  fromDraft,
  saveProfile,
  TRAINING_CHECKS,
  type ProfileDraft,
} from "@/app/lib/profile";

const steps = [
  {
    title: "About you",
    intro: "Your body measurements help us read your stroke from video.",
    Fields: BodyFields,
    check: (d: ProfileDraft) => checkDraft(d, BODY_CHECKS),
  },
  {
    title: "Your swimming",
    intro: "So feedback matches your experience.",
    Fields: LevelField,
    check: checkLevel,
  },
  {
    title: "Your training",
    intro: "How often and how long you're in the water.",
    Fields: TrainingFields,
    check: (d: ProfileDraft) => checkDraft(d, TRAINING_CHECKS),
  },
  {
    title: "Personal bests",
    intro: "Where you're starting from, so we can track your progress.",
    Fields: PbFields,
    check: checkPbs,
  },
];

// Profile survey shown right after signup. Answers are saved to the user's profile.
export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<ProfileDraft>(emptyDraft);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const { title, intro, Fields, check } = steps[step];
  const last = step === steps.length - 1;

  useEffect(
    () =>
      onAuthStateChanged(auth, (u) => {
        if (u) setUser(u);
        else router.replace("/login");
      }),
    [router],
  );

  function set(changes: Partial<ProfileDraft>) {
    setDraft((d) => ({ ...d, ...changes }));
    setError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    const problem = check(draft);
    if (problem) return setError(problem);
    if (!last) return setStep(step + 1);
    if (!user) return;

    setPending(true);
    try {
      await saveProfile(user.uid, fromDraft(draft));
    } catch (err) {
      setPending(false);
      return setError(describeFirebaseError(err));
    }
    router.replace("/");
  }

  return (
    <div className="relative flex min-h-screen flex-1 flex-col overflow-hidden bg-gradient-to-b from-sky-50 to-cyan-50">
      <svg
        aria-hidden="true"
        viewBox="0 0 400 100"
        preserveAspectRatio="none"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-40 w-full text-sky-200/60"
      >
        {[30, 60, 90].map((y) => (
          <path
            key={y}
            d={`M0 ${y} Q50 ${y - 10} 100 ${y} T200 ${y} T300 ${y} T400 ${y}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
          />
        ))}
      </svg>

      <header className="relative px-4 py-5 sm:px-8">
        <Logo className="text-sky-800" />
      </header>

      <main className="relative flex flex-1 items-start justify-center px-4 pb-16 sm:items-center sm:px-8">
        <div className="w-full max-w-xl">
          {/* Lane-style step indicator */}
          <ol className="mb-6 grid grid-cols-4 gap-2" aria-label="Survey steps">
            {steps.map((s, i) => (
              <li key={s.title}>
                <span
                  className={`block h-1.5 rounded-full ${i <= step ? "bg-sky-600" : "bg-sky-200"}`}
                />
                <span
                  className={`mt-2 hidden text-xs font-medium sm:block ${i === step ? "text-sky-800" : "text-slate-500"}`}
                >
                  {s.title}
                </span>
              </li>
            ))}
          </ol>

          <form
            onSubmit={onSubmit}
            noValidate
            className="rounded-2xl border border-slate-200 bg-surface p-6 shadow-sm sm:p-8"
          >
            <p className="text-sm font-medium text-sky-700">
              Step {step + 1} of {steps.length}
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
            <p className="mt-1 mb-6 text-slate-600">{intro}</p>

            <div className="space-y-5">
              <FormError message={error} />
              <Fields draft={draft} set={set} />
            </div>

            <div className="mt-8 flex items-center justify-between gap-3">
              {step > 0 ? (
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setStep(step - 1);
                  }}
                  className="rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100"
                >
                  Back
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => router.replace("/")}
                  className="rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-500 hover:bg-slate-100"
                >
                  Skip for now
                </button>
              )}
              <button
                type="submit"
                disabled={pending}
                className="rounded-lg bg-sky-700 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-sky-800 focus:outline-none focus:ring-4 focus:ring-sky-600/30 disabled:opacity-70"
              >
                {pending
                  ? "Saving…"
                  : !last
                    ? "Continue"
                    : draft.pbs.some((pb) => pb.time.trim())
                      ? "Finish"
                      : "Skip and finish"}
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
