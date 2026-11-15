import { api, type ApiResult } from "@/app/lib/api";
import {
  parseComparison,
  parseProgress,
  type ProgressView,
  type SessionComparison,
} from "@/app/lib/history";

export async function fetchProgress(): Promise<ApiResult<ProgressView | null>> {
  const res = await api<unknown>("/progress");
  return res.ok ? { ok: true, data: parseProgress(res.data) } : res;
}

export async function fetchComparison(
  a: string,
  b: string,
): Promise<ApiResult<SessionComparison | null>> {
  const res = await api<unknown>(
    `/videos/${encodeURIComponent(a)}/compare/${encodeURIComponent(b)}`,
  );
  return res.ok ? { ok: true, data: parseComparison(res.data) } : res;
}

// Deletes one of the swimmer's own videos and everything stored for it. Safe to repeat.
export function deleteVideo(
  id: string,
): Promise<ApiResult<{ deleted: boolean }>> {
  return api<{ deleted: boolean }>(`/videos/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
