// Browser client for the Sokhan REST API. The dashboard authenticates with
// the httpOnly session cookie the API sets at sign-in: script never sees the
// token, every request goes out with credentials, and writes carry the
// session's CSRF token. A 401 marks the session signed out and bounces the
// user back to the login screen.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

/** Fired on this tab whenever the session state changes. */
export const SESSION_CHANGE_EVENT = "sokhan:session-change";
// Earlier versions kept the token in localStorage; it is wiped on load.
const LEGACY_STORAGE_KEYS = ["sokhan_token", "sokhan_email"];
const SAFE_METHODS = new Set(["GET", "HEAD"]);

export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type TranscriptFormat = "txt" | "srt" | "vtt" | "json" | "docx";

export interface AuthResponse {
  id: string;
  email: string;
  api_token: string;
  csrf_token: string | null;
}

export interface SessionState {
  /** "unknown" until GET /auth/session has answered once. */
  status: "unknown" | "signedIn" | "signedOut";
  email: string | null;
  csrfToken: string | null;
}

export interface QuotaInfo {
  plan: string;
  plan_expires_at: string | null;
  max_file_minutes: number;
  limit_minutes: number;
  used_minutes: number;
  remaining_minutes: number;
  month: string;
}

export interface UploadResult {
  id: string;
  status: string;
}

export interface JobListItem {
  id: string;
  filename: string;
  status: JobStatus;
  progress: number;
  duration_seconds: number;
  created_at: string;
  has_summary: boolean;
}

export interface JobListResponse {
  items: JobListItem[];
  total: number;
}

export interface TranscriptSegment {
  position: number;
  start: number;
  end: number;
  speaker: string | null;
  /** Model confidence exp(avg_logprob) in (0, 1]; null when unavailable. */
  confidence: number | null;
  text: string;
}

export interface JobDetail {
  id: string;
  filename: string;
  status: JobStatus;
  progress: number;
  error: string | null;
  duration_seconds: number;
  language: string;
  created_at: string;
  completed_at: string | null;
  has_summary: boolean;
  summary: string | null;
  text: string | null;
  segments?: TranscriptSegment[];
}

export class ApiError extends Error {
  readonly status: number;
  /** Machine-readable code from a structured FastAPI `detail` (e.g. "file_too_long"). */
  readonly code: string | null;
  /** The full structured detail object when the API sent one. */
  readonly detail: Record<string, unknown> | null;

  constructor(
    status: number,
    message?: string,
    code: string | null = null,
    detail: Record<string, unknown> | null = null,
  ) {
    super(message ?? `API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

const UNKNOWN_SESSION: SessionState = { status: "unknown", email: null, csrfToken: null };
const SIGNED_OUT: SessionState = { status: "signedOut", email: null, csrfToken: null };

let session: SessionState = UNKNOWN_SESSION;
let sessionRequest: Promise<void> | null = null;
let otherTabs: BroadcastChannel | null = null;

function setSession(next: SessionState, broadcast = true): void {
  session = next;
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(SESSION_CHANGE_EVENT));
  if (broadcast) otherTabs?.postMessage("changed");
}

/** The current session snapshot; a new object only when it changes. */
export function getSessionState(): SessionState {
  return session;
}

/** The server snapshot: nothing is known before hydration. */
export function getUnknownSessionState(): SessionState {
  return UNKNOWN_SESSION;
}

/** Ask the API who is signed in (deduplicated while a request is in flight). */
export function loadSession(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (!otherTabs && "BroadcastChannel" in window) {
    otherTabs = new BroadcastChannel("sokhan-session");
    otherTabs.onmessage = () => {
      sessionRequest = null;
      void loadSession();
    };
    for (const key of LEGACY_STORAGE_KEYS) {
      try {
        window.localStorage.removeItem(key);
      } catch {
        // Storage disabled: nothing to clean up.
      }
    }
  }
  sessionRequest ??= (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/session`, { credentials: "include" });
      if (!response.ok) {
        setSession(SIGNED_OUT, false);
        return;
      }
      const body = (await response.json()) as { email: string; csrf_token: string };
      setSession({ status: "signedIn", email: body.email, csrfToken: body.csrf_token }, false);
    } catch {
      setSession(SIGNED_OUT, false);
    } finally {
      sessionRequest = null;
    }
  })();
  return sessionRequest;
}

/** Record a successful sign-in; the API has already set the cookie. */
export function startSession(auth: AuthResponse): void {
  setSession({ status: "signedIn", email: auth.email, csrfToken: auth.csrf_token });
}

function csrfHeaders(method: string, headers: Headers): Headers {
  if (!SAFE_METHODS.has(method) && session.csrfToken) {
    headers.set("X-CSRF-Token", session.csrfToken);
  }
  return headers;
}

/**
 * Revoke the session on the server (which also clears the cookie), then
 * mark it signed out locally. The local sign-out happens even when the API
 * is unreachable, so signing out always works from the user's point of view.
 */
export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: csrfHeaders("POST", new Headers()),
    });
  } catch {
    // Offline or API down: the local sign-out below still happens.
  }
  setSession(SIGNED_OUT);
}

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const firstSegment = window.location.pathname.split("/")[1];
  const locale = firstSegment === "en" ? "en" : "fa";
  window.location.assign(`/${locale}/login`);
}

function handleAuthFailure(response: Response): void {
  if (response.status === 401) {
    setSession(SIGNED_OUT);
    redirectToLogin();
  }
}

interface RequestOptions {
  method?: string;
  body?: BodyInit;
  headers?: Record<string, string>;
  authenticated?: boolean;
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers: extraHeaders, authenticated = false } = options;

  const headers = csrfHeaders(method, new Headers(extraHeaders));

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "network error");
  }

  if (authenticated) handleAuthFailure(response);
  if (!response.ok) {
    // FastAPI errors carry either a plain-string detail or a structured
    // object ({ code, ... }); surface both so callers can react to codes
    // like "quota_exceeded" and "file_too_long".
    let message: string | undefined;
    let code: string | null = null;
    let detail: Record<string, unknown> | null = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body && typeof body === "object" && "detail" in body) {
        const raw = body.detail;
        if (typeof raw === "string") {
          message = raw;
        } else if (raw && typeof raw === "object") {
          detail = raw as Record<string, unknown>;
          if (typeof detail.code === "string") code = detail.code;
        }
      }
    } catch {
      // Body was not JSON; fall back to the generic status message.
    }
    throw new ApiError(response.status, message, code, detail);
  }

  return (await response.json()) as T;
}

export async function register(email: string, password: string): Promise<AuthResponse> {
  return requestJson("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  return requestJson("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function tokenLogin(apiToken: string): Promise<AuthResponse> {
  return requestJson("/auth/token-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_token: apiToken }),
  });
}

export async function getQuota(): Promise<QuotaInfo> {
  return requestJson("/quota", { authenticated: true });
}

export async function uploadJob(
  file: File,
  options: { language: string; wantSummary: boolean },
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("language", options.language);
  form.append("want_summary", options.wantSummary ? "true" : "false");

  return requestJson("/jobs", {
    method: "POST",
    body: form,
    authenticated: true,
  });
}

export async function listJobs(): Promise<JobListResponse> {
  return requestJson("/jobs", { authenticated: true });
}

export async function getJob(id: string): Promise<JobDetail> {
  return requestJson(`/jobs/${encodeURIComponent(id)}`, { authenticated: true });
}

export async function searchJobs(query: string): Promise<JobListResponse> {
  return requestJson(`/search?q=${encodeURIComponent(query)}`, { authenticated: true });
}

export async function deleteJob(id: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/jobs/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: csrfHeaders("DELETE", new Headers()),
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "network error");
  }

  handleAuthFailure(response);
  if (!response.ok) throw new ApiError(response.status);
}

export async function downloadTranscript(id: string, format: TranscriptFormat): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/jobs/${encodeURIComponent(id)}/transcript?format=${format}`,
      { credentials: "include" },
    );
  } catch {
    throw new ApiError(0, "network error");
  }

  handleAuthFailure(response);
  if (!response.ok) throw new ApiError(response.status);

  return await response.blob();
}
