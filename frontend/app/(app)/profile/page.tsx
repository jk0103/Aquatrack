"use client";

import { useState, type FormEvent } from "react";

import { useUser } from "@/app/components/AppShell";
import { AboutFields, GoalFields, SwimmingFields, TimesFields } from "@/app/components/ProfileFields";
import { Badge, Button, Card, PageHeader } from "@/app/components/ui";
import { formatTime, profile, progression } from "@/app/lib/mock";

export default function ProfilePage() {
  const user = useUser();
  const [editing, setEditing] = useState(false);
  const name = user?.name ?? profile.name;
  const email = user?.email ?? profile.email;
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  // Layout only: closes the editor without saving.
  function onSave(event: FormEvent) {
    event.preventDefault();
    setEditing(false);
  }

  return (
    <>
      <PageHeader
        title={editing ? "Edit profile" : "Profile"}
        action={
          !editing && (
            <Button variant="secondary" className="self-start" onClick={() => setEditing(true)}>
              Edit profile
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
            <p className="truncate text-sm text-sky-100">{email}</p>
            {editing && (
              <button className="mt-1 text-sm font-medium text-cyan-200 hover:text-white">
                Change photo
              </button>
            )}
          </div>
        </div>
      </section>

      {editing ? (
        <form onSubmit={onSave} className="space-y-6">
          <Card title="Name and email">
            <div className="grid gap-5 sm:grid-cols-2">
              <label className="block space-y-1.5">
                <span className="block text-sm font-medium text-slate-700">Name</span>
                <input
                  defaultValue={name}
                  className="block w-full rounded-lg border border-slate-300 px-3.5 py-2.5 shadow-sm focus:border-sky-600 focus:outline-none focus:ring-4 focus:ring-sky-600/15"
                />
              </label>
              <label className="block space-y-1.5">
                <span className="block text-sm font-medium text-slate-700">Email</span>
                <input
                  type="email"
                  defaultValue={email}
                  className="block w-full rounded-lg border border-slate-300 px-3.5 py-2.5 shadow-sm focus:border-sky-600 focus:outline-none focus:ring-4 focus:ring-sky-600/15"
                />
              </label>
            </div>
          </Card>
          <Card title="About you">
            <AboutFields d={profile} />
          </Card>
          <Card title="Your swimming">
            <SwimmingFields d={profile} />
          </Card>
          <Card title="Goals">
            <GoalFields d={profile} />
          </Card>
          <Card title="Best times">
            <TimesFields />
          </Card>
          <div className="sticky bottom-20 z-10 flex justify-end gap-3 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur sm:bottom-4">
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
            <Button type="submit">Save changes</Button>
          </div>
        </form>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Swimming" className="lg:col-span-2">
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Item label="Level" value={profile.level} />
              <Item label="Club" value={profile.club} />
              <Item label="Usual pool" value={profile.poolLength} />
              <Item label="Sessions per week" value={String(profile.sessionsPerWeek)} />
              <div className="sm:col-span-2">
                <dt className="text-sm text-slate-500">Strokes</dt>
                <dd className="mt-1.5 flex flex-wrap gap-2">
                  {profile.strokes.map((s) => (
                    <Badge key={s} tone={s === profile.primaryStroke ? "sky" : "slate"}>
                      {s}
                      {s === profile.primaryStroke ? " · main" : ""}
                    </Badge>
                  ))}
                </dd>
              </div>
            </dl>
          </Card>

          <Card title="Goal">
            <p className="text-slate-800">{profile.goal}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge tone="teal">Speed</Badge>
              <Badge tone="teal">Technique</Badge>
            </div>
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
      <dd className="mt-0.5 font-medium text-slate-900">{value}</dd>
    </div>
  );
}
