"use client";

import { useEffect, useState, type FormEvent } from "react";

import { useUser } from "@/app/components/AppShell";
import { FormError } from "@/app/components/fields";
import { BodyFields, LevelField, TrainingFields } from "@/app/components/ProfileFields";
import { Badge, Button, ButtonLink, Card, PageHeader } from "@/app/components/ui";
import { describeFirebaseError } from "@/app/lib/firebase";
import { formatTime, progression } from "@/app/lib/mock";
import {
  BODY_CHECKS,
  checkDraft,
  checkLevel,
  emptyDraft,
  formatMinutes,
  fromDraft,
  levelLabel,
  loadProfile,
  saveProfile,
  toDraft,
  TRAINING_CHECKS,
  type Profile,
  type ProfileDraft,
} from "@/app/lib/profile";

export default function ProfilePage() {
  const user = useUser();
  // undefined while loading, null when the survey hasn't been filled in.
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ProfileDraft>(emptyDraft);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const uid = user?.uid;
  useEffect(() => {
    if (!uid) return;
    loadProfile(uid)
      .then(setProfile)
      .catch((err) => setLoadError(describeFirebaseError(err)));
  }, [uid]);

  const name = user?.name ?? "";
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");

  function startEditing() {
    setDraft(profile ? toDraft(profile) : emptyDraft);
    setError(null);
    setEditing(true);
  }

  function set(changes: Partial<ProfileDraft>) {
    setDraft((d) => ({ ...d, ...changes }));
    setError(null);
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    if (pending || !uid) return;
    const problem =
      checkDraft(draft, BODY_CHECKS) ?? checkLevel(draft) ?? checkDraft(draft, TRAINING_CHECKS);
    if (problem) return setError(problem);

    setPending(true);
    const saved = fromDraft(draft);
    try {
      await saveProfile(uid, saved);
    } catch (err) {
      return setError(describeFirebaseError(err));
    } finally {
      setPending(false);
    }
    setProfile(saved);
    setEditing(false);
  }

  return (
    <>
      <PageHeader
        title={editing ? "Edit profile" : "Profile"}
        action={
          !editing &&
          profile !== undefined && (
            <Button variant="secondary" className="self-start" onClick={startEditing}>
              {profile ? "Edit profile" : "Fill in profile"}
            </Button>
          )
        }
      />

      <section className="relative mb-6 overflow-hidden rounded-2xl bg-gradient-to-r from-sky-800 to-cyan-700 p-6 text-white shadow-sm">
        <div className="relative z-10 flex items-center gap-4">
          <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-white/15 text-xl font-semibold ring-2 ring-white/30">
            {initials}
          </span>
          <div className="min-w-0">
            <p className="truncate text-xl font-semibold">{name}</p>
            <p className="truncate text-sm text-sky-100">{user?.email}</p>
            {profile && (
              <span className="mt-2 inline-block rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-medium">
                {levelLabel(profile.swim_level)} swimmer
              </span>
            )}
          </div>
        </div>
      </section>

      {loadError ? (
        <FormError message={loadError} />
      ) : profile === undefined ? (
        <p className="text-slate-500">Loading…</p>
      ) : editing ? (
        <form onSubmit={onSave} noValidate className="space-y-6">
          <FormError message={error} />
          <Card title="About you">
            <BodyFields draft={draft} set={set} />
          </Card>
          <Card title="Your swimming">
            <LevelField draft={draft} set={set} />
          </Card>
          <Card title="Your training">
            <TrainingFields draft={draft} set={set} />
          </Card>
          <div className="sticky bottom-20 z-10 flex justify-end gap-3 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur sm:bottom-4">
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
            <Button type="submit">{pending ? "Saving…" : "Save changes"}</Button>
          </div>
        </form>
      ) : profile === null ? (
        <Card>
          <p className="font-medium text-slate-900">You haven&apos;t filled in your profile yet.</p>
          <p className="mt-1 mb-4 text-sm text-slate-600">
            It takes a minute and helps us tailor feedback and training plans to you.
          </p>
          <ButtonLink href="/onboarding">Start the survey</ButtonLink>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="About you">
            <dl className="grid grid-cols-3 gap-4 lg:grid-cols-1">
              <Item label="Age" value={`${profile.age}`} />
              <Item label="Height" value={`${profile.height_cm} cm`} />
              <Item label="Weight" value={`${profile.weight_kg} kg`} />
            </dl>
          </Card>

          <Card title="Swimming">
            <Badge>{levelLabel(profile.swim_level)}</Badge>
          </Card>

          <Card title="Training">
            <dl className="grid grid-cols-2 gap-4 lg:grid-cols-1">
              <Item label="Times a week" value={`${profile.sessions_per_week}`} />
              <Item label="Time per day" value={formatMinutes(profile.minutes_per_day)} />
            </dl>
          </Card>

          <Card title="Best times" className="lg:col-span-3">
            <ul className="grid gap-3 sm:grid-cols-3">
              {Object.entries(progression).map(([event, entries]) => (
                <li key={event} className="rounded-xl bg-sky-50 p-4">
                  <p className="text-sm text-sky-800">{event}</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {formatTime(Math.min(...entries.map((e) => e.seconds)))}
                  </p>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold text-slate-900">{value}</dd>
    </div>
  );
}
