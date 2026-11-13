// Browser client for the Sokhan REST API. Authenticated requests carry the
// stored API token as a Bearer header; a 401 clears the token and bounces
// the user back to the login screen.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export const TOKEN_STORAGE_KEY = "sokhan_token";

export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type TranscriptFormat = "txt" | "srt" | "docx";

export interface AuthResponse {
  id: string;
  email: string;
  api_token: string;
}

export interface QuotaInfo {
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
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message?: string) {
    super(message ?? `API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
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
  if (!response.ok) throw new ApiError(response.status);

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
