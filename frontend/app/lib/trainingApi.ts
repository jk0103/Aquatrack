import { api, type ApiResult } from "@/app/lib/api";
import {
  localIso,
  parseCalendar,
  parseOverview,
  parsePlan,
  parseSaveResult,
  parseSession,
  type CalendarFeed,
  type DraftItem,
  type SaveResult,
  type TrainingOverview,
  type TrainingPlan,
  type TrainingSession,
} from "@/app/lib/training";

const UNREADABLE = { ok: false as const, status: 0, error: "The server's answer could not be read." };

function read<T>(res: ApiResult<unknown>, parse: (raw: unknown) => T | null): ApiResult<T> {
  if (!res.ok) return res;
  const data = parse(res.data);
  return data === null ? UNREADABLE : { ok: true, data };
}

const post = (body: unknown, method = "POST"): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

// "Today" is the date on the swimmer's own device, so a plan never starts on the wrong day.
export async function fetchTraining(): Promise<ApiResult<TrainingOverview>> {
  return read(await api<unknown>(`/training?today=${localIso(new Date())}`), parseOverview);
}

export async function previewPlan(
  kind: "session" | "week",
  start: string,
): Promise<ApiResult<TrainingPlan>> {
  return read(await api<unknown>("/training/plans/preview", post({ kind, start })), parsePlan);
}

// `token` comes from the preview being saved: if the schedule changed since, the backend
// refuses rather than saving a plan the swimmer has not seen in its current form.
export async function savePlan(
  kind: "session" | "week",
  start: string,
  token: string,
  opts: { confirm?: boolean; discard_edits?: boolean } = {},
): Promise<ApiResult<SaveResult>> {
  return read(
    await api<unknown>("/training/plans", post({ kind, start, token, ...opts })),
    parseSaveResult,
  );
}

export async function fetchCalendar(start: string, end: string): Promise<ApiResult<CalendarFeed>> {
  return read(await api<unknown>(`/training/calendar?start=${start}&end=${end}`), parseCalendar);
}

export type SessionChange = {
  date?: string;
  time?: string;
  title?: string;
  items?: DraftItem[];
  status?: "planned" | "skipped" | "canceled";
};

// Every change names the revision it was made from. If the session was changed in another
// tab or on another device since, the backend answers 409 and nothing is overwritten.
export async function updateSession(
  id: string,
  revision: number,
  change: SessionChange,
): Promise<ApiResult<TrainingSession>> {
  return read(
    await api<unknown>(
      `/training/sessions/${encodeURIComponent(id)}`,
      post({ ...change, revision }, "PATCH"),
    ),
    parseSession,
  );
}

export async function createSession(body: {
  date: string;
  time: string;
  title: string;
  items: DraftItem[];
  allow_duplicate?: boolean;
}): Promise<ApiResult<TrainingSession>> {
  return read(await api<unknown>("/training/sessions", post(body)), parseSession);
}

export async function completeSession(
  id: string,
  body: { revision: number; completed_on: string; done: number[]; note: string; video_id: string },
): Promise<ApiResult<TrainingSession>> {
  return read(
    await api<unknown>(`/training/sessions/${encodeURIComponent(id)}/complete`, post(body)),
    parseSession,
  );
}

export function deleteSession(
  id: string,
  revision: number,
): Promise<ApiResult<{ deleted: boolean }>> {
  return api<{ deleted: boolean }>(
    `/training/sessions/${encodeURIComponent(id)}?revision=${revision}`,
    { method: "DELETE" },
  );
}

// Deletes the swimmer's whole account and everything it owns. Needs the exact phrase.
export function deleteAccount(confirm: string): Promise<ApiResult<{ deleted: boolean }>> {
  return api<{ deleted: boolean }>("/me", { method: "DELETE", body: JSON.stringify({ confirm }) });
}
