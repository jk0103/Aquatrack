import { auth } from "@/app/lib/firebase";

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string; status: number };

type FastApiError = { detail?: string | { msg: string; loc: (string | number)[] }[] };

function describeError(body: FastApiError | null, status: number): string {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const field = detail[0].loc.at(-1);
    return field ? `${field}: ${detail[0].msg}` : detail[0].msg;
  }
  return status >= 500 ? "Something went wrong on our side. Try again." : "Request failed.";
}

// Calls the FastAPI backend as the logged-in Firebase user.
export async function api<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let res: Response;
  try {
    const token = await auth.currentUser?.getIdToken();
    res = await fetch(`/api${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    return { ok: false, status: 0, error: "Can't reach the server. Check your connection." };
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) return { ok: false, status: res.status, error: describeError(body, res.status) };
  return { ok: true, data: body as T };
}
