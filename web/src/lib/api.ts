// Browser client for the Sokhan REST API. Authenticated requests carry the
// stored API token as a Bearer header; a 401 clears the token and bounces
// the user back to the login screen.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export const TOKEN_STORAGE_KEY = "sokhan_token";
export const EMAIL_STORAGE_KEY = "sokhan_email";
/** Fired on this tab whenever the stored session changes (sign-in or out). */
export const SESSION_CHANGE_EVENT = "sokhan:session-change";

export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type TranscriptFormat = "txt" | "srt" | "vtt" | "json" | "docx";

export interface AuthResponse {
  id: string;
  email: string;
  api_token: string;
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

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(EMAIL_STORAGE_KEY);
}

function notifySessionChange(): void {
  window.dispatchEvent(new Event(SESSION_CHANGE_EVENT));
}

export function setToken(token: string, email?: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  if (email) window.localStorage.setItem(EMAIL_STORAGE_KEY, email);
  else window.localStorage.removeItem(EMAIL_STORAGE_KEY);
  notifySessionChange();
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(EMAIL_STORAGE_KEY);
  notifySessionChange();
}

/**
 * Revoke the token on the server, then forget it locally. The local
 * session is cleared even when the API is unreachable or already rejects
 * the token, so signing out always works from the user's point of view.
 */
export async function logout(): Promise<void> {
  const token = getToken();
  if (token) {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      // Offline or API down: the local sign-out below still happens.
    }
  }
  clearToken();
}

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const firstSegment = window.location.pathname.split("/")[1];
  const locale = firstSegment === "en" ? "en" : "fa";
  window.location.assign(`/${locale}/login`);
}

function handleAuthFailure(response: Response): void {
  if (response.status === 401) {
    clearToken();
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

  const headers = new Headers(extraHeaders);
  if (authenticated) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method, headers, body });
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
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/jobs/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers,
    });
  } catch {
    throw new ApiError(0, "network error");
  }

  handleAuthFailure(response);
  if (!response.ok) throw new ApiError(response.status);
}

export async function downloadTranscript(id: string, format: TranscriptFormat): Promise<Blob> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/jobs/${encodeURIComponent(id)}/transcript?format=${format}`,
      { headers },
    );
  } catch {
    throw new ApiError(0, "network error");
  }

  handleAuthFailure(response);
  if (!response.ok) throw new ApiError(response.status);

  return await response.blob();
}
