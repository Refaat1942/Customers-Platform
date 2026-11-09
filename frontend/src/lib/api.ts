const TOKEN_KEY = "cp_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* */ }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export type Params = Record<string, string | number | boolean | null | undefined | string[]>;

export function qs(params: Params = {}): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, x));
    else u.append(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

async function request(method: string, path: string, body?: unknown, raw = false): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData || body instanceof Blob) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  if (res.status === 401 && !path.startsWith("/auth/login")) onUnauthorized();
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join(", ") : msg;
    } catch { /* not json */ }
    throw new ApiError(res.status, msg);
  }
  return raw ? res : res;
}

export const api = {
  get: async <T = any>(path: string, params?: Params): Promise<T> => (await request("GET", path + qs(params))).json(),
  post: async <T = any>(path: string, body?: unknown): Promise<T> => (await request("POST", path, body)).json(),
  put: async <T = any>(path: string, body?: unknown): Promise<T> => (await request("PUT", path, body)).json(),
  del: async <T = any>(path: string): Promise<T> => (await request("DELETE", path)).json(),
  raw: request,
};

/** Download an Excel export (authenticated) and save it with the server's file name. */
export async function download(path: string, params: Params) {
  const res = await request("GET", path + qs({ ...params, export: true }));
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const name = /filename="?([^"]+)"?/.exec(cd)?.[1] || "report.xlsx";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
