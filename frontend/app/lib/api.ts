export type User = { id: number; name: string; email: string };

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string; status: number };

type FastApiError = { detail?: string | { msg: string; loc: (string | number)[] }[] };

function describeError(body: FastApiError | null, status: number): string {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const field = detail[0].loc.at(-1);
    if (field === "email") return "Enter a valid email address.";
    if (field === "password") return "Password must be at least 8 characters.";
    if (field === "name") return "Enter your name.";
    return detail[0].msg;
  }
  return status >= 500 ? "Something went wrong on our side. Try again." : "Request failed.";
}

export async function api<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      credentials: "same-origin",
    });
  } catch {
    return { ok: false, status: 0, error: "Can't reach the server. Check your connection." };
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) return { ok: false, status: res.status, error: describeError(body, res.status) };
  return { ok: true, data: body as T };
}
