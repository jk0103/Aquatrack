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

export async function savePlan(
  kind: "session" | "week",
  start: string,
  opts: { confirm?: boolean; discard_edits?: boolean } = {},
): Promise<ApiResult<SaveResult>> {
  return read(await api<unknown>("/training/plans", post({ kind, start, ...opts })), parseSaveResult);
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

export async function updateSession(
  id: string,
  change: SessionChange,
): Promise<ApiResult<TrainingSession>> {
  return read(
    await api<unknown>(`/training/sessions/${encodeURIComponent(id)}`, post(change, "PATCH")),
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
  body: { completed_on: string; done: number[]; note: string; video_id: string },
): Promise<ApiResult<TrainingSession>> {
  return read(
    await api<unknown>(`/training/sessions/${encodeURIComponent(id)}/complete`, post(body)),
    parseSession,
  );
}

export function deleteSession(id: string): Promise<ApiResult<{ deleted: boolean }>> {
  return api<{ deleted: boolean }>(`/training/sessions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
