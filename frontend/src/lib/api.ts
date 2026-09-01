/**
 * API client.
 *
 * Single fetch wrapper so JWT attachment, error shaping and 401 handling live
 * in one place rather than being re-implemented per call site.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";
const TOKEN_KEY = "srts_token";

export class ApiError extends Error {
  // Explicit fields rather than TS parameter properties: this project's
  // tsconfig enables `erasableSyntaxOnly`, which forbids the shorthand.
  status: number;
  detail?: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      // Private-mode browsers can throw on storage access. Treat as logged out
      // rather than crashing the app shell.
      return null;
    }
  },
  set(token: string) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* non-fatal: session simply will not survive a reload */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* non-fatal */
    }
  },
};

/** Fires when the API rejects our token, so AuthProvider can log the user out. */
type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  onUnauthorized = handler;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Skip the 401 -> logout side effect (used by the login call itself). */
  skipAuthRedirect?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, skipAuthRedirect } = options;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // Network-level failure: the backend is down or unreachable. Say so
    // explicitly -- "Failed to fetch" is not an actionable message.
    throw new ApiError(0, "Cannot reach the API. Is the backend running on port 8000?");
  }

  if (response.status === 401 && !skipAuthRedirect) {
    tokenStore.clear();
    onUnauthorized?.();
    throw new ApiError(401, "Session expired. Please sign in again.");
  }

  if (!response.ok) {
    let detail: unknown;
    let message = `Request failed (${response.status})`;
    try {
      const parsed = await response.json();
      detail = parsed?.detail ?? parsed;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail) && detail[0]?.msg) {
        // FastAPI validation error array.
        message = detail.map((d: { msg: string }) => d.msg).join("; ");
      }
    } catch {
      /* body was not JSON; keep the generic message */
    }
    throw new ApiError(response.status, message, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T,>(path: string) => apiRequest<T>(path),
  post: <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: "POST", body }),
  patch: <T,>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  del: <T,>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
};

/** Build a query string, dropping empty/undefined values. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}
