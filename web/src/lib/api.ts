/** Typed API client — mirrors the backend Pydantic schemas. */

export interface UserPublic {
  id: number;
  username: string;
  display_name: string | null;
  role: "admin" | "operator" | "viewer";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AccountStats {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  items_collected: number;
}

export interface XAccount {
  id: number;
  label: string;
  notes: string | null;
  status: "active" | "cooldown" | "disabled" | "invalid";
  health_score: number;
  proxy_id: number | null;
  stats: AccountStats;
  has_cookies: boolean;
  cookie_updated_at: string | null;
  last_run_at: string | null;
  cooldown_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface Proxy {
  id: number;
  label: string | null;
  url: string;
  status: "active" | "disabled";
  latency_ms: number | null;
  last_check_at: string | null;
  created_at: string;
}

export type JobType = "search" | "timeline" | "news" | "monitor" | "composite";
export type ScheduleKind = "manual" | "interval" | "daily";
export type Aggressiveness = "cautious" | "balanced" | "fast";

export interface TimelineTabConfig {
  tab: string;
  max_items: number;
  max_scrolls?: number | null;
}

export interface JobConfig {
  search?: { keywords: string[]; max_items_per_keyword: number } | null;
  timeline?: TimelineTabConfig[] | null;
  news?: { detail: boolean; max_items: number } | null;
  monitor?: {
    users: { username: string; only_new: boolean; max_tweets: number }[];
    global_max: number;
  } | null;
}

export interface ScheduleSpec {
  kind: ScheduleKind;
  interval_minutes?: number | null;
  daily_at?: string | null;
}

export interface Job {
  id: number;
  name: string;
  type: JobType;
  config: JobConfig;
  schedule: ScheduleSpec;
  anti_ban: { aggressiveness: Aggressiveness };
  account_id: number | null;
  status: "active" | "paused";
  priority: number;
  next_run_at: string | null;
  last_run_at: string | null;
  stats: Record<string, number>;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface JobCreatePayload {
  name: string;
  type: JobType;
  config: JobConfig;
  schedule: ScheduleSpec;
  anti_ban: { aggressiveness: Aggressiveness };
  account_id?: number | null;
  priority?: number;
}

export interface Run {
  id: number;
  job_id: number;
  job_name: string | null;
  account_id: number | null;
  account_label: string | null;
  status: "queued" | "running" | "success" | "empty" | "failed" | "timeout" | "cancelled" | "skipped";
  started_at: string | null;
  finished_at: string | null;
  items_new: number;
  items_total: number;
  outcome: { kind: string; message?: string | null; signals?: string[] } | null;
  duration_ms: number | null;
  log_excerpt: string | null;
}

export interface RunPage {
  items: Run[];
  total: number;
}

export interface PostAuthor {
  username: string;
  nickname: string | null;
  avatar_url: string | null;
}

export interface Post {
  id: string;
  author: PostAuthor;
  content: string;
  description: string | null;
  url: string | null;
  source: string;
  is_article: boolean;
  stats: { likes: number; comments: number; shares: number; views: number };
  media: { type: string; url: string; cover_url: string | null }[];
  publish_time: string | null;
  crawl_time: string | null;
}

export interface PostFilterState {
  q?: string;
  author?: string;
  sources?: string[];
  date_from?: string;
  date_to?: string;
  min_likes?: number;
  min_views?: number;
  has_media?: boolean;
  sort: "publish_time" | "likes" | "views" | "crawl_time";
  order: "asc" | "desc";
  page: number;
  page_size: number;
}

export interface PostPage {
  items: Post[];
  total: number;
  page: number;
  page_size: number;
}

export interface Author {
  username: string;
  nickname: string | null;
  avatar_url: string | null;
  profile_url: string | null;
  posts_count: number;
  first_seen: string | null;
  last_seen: string | null;
}

export interface AuthorPage {
  items: Author[];
  total: number;
  page: number;
  page_size: number;
}

export interface AppEvent {
  id: number | null;
  ts: string;
  type: string;
  level: "info" | "success" | "warning" | "error";
  category: string;
  message: string;
  params: Record<string, unknown> | null;
  account_id: number | null;
  job_id: number | null;
  run_id: number | null;
}

export interface AppSettings {
  anti_ban: {
    min_run_gap_minutes: number;
    gap_jitter_fraction: number;
    global_min_gap_minutes: number;
    max_concurrent_runs: number;
    max_runs_per_account_per_day: number;
    run_timeout_minutes: number;
    backoff_base_minutes: number;
    backoff_cap_minutes: number;
    rate_limit_cooldown_minutes: number;
    empty_result_cooldown_minutes: number;
    error_cooldown_minutes: number;
    health_on_success: number;
    health_on_empty: number;
    health_on_rate_limited: number;
    health_on_error: number;
    disable_health_threshold: number;
    auth_failure_disable_threshold: number;
    warmup_runs: number;
    warmup_gap_multiplier: number;
  };
  schedule: { enabled: boolean; start: string; end: string };
  risk: {
    window_minutes: number;
    min_runs_for_eval: number;
    yellow_failure_rate: number;
    red_failure_rate: number;
    red_rate_limited_count: number;
    red_auth_expired_count: number;
    auto_resume_minutes: number;
  };
  crawler: { headless: boolean; default_max_scrolls: number; keep_raw_items: boolean };
  retention: { events_days: number; finished_runs_days: number };
}

export interface RiskState {
  level: "green" | "yellow" | "red";
  reasons: string[];
  paused: boolean;
  paused_since: string | null;
  auto_resume_at: string | null;
}

export interface Overview {
  totals: {
    posts: number;
    authors: number;
    accounts_total: number;
    accounts_active: number;
    accounts_invalid: number;
    jobs_total: number;
    jobs_active: number;
  };
  today: { runs: number; successful_runs: number; items_new: number };
  risk: RiskState;
  engine_running: boolean;
  collection_14d: { date: string; count: number }[];
  top_authors: Author[];
  recent_runs: Run[];
}

export interface SystemStatus {
  version: string;
  environment: string;
  crawlfox_bin: string;
  crawlfox_available: boolean;
  camoufox_fetched: boolean;
  database_ok: boolean;
  data_dir: string;
  disk_free_gb: number | null;
  uptime_seconds: number;
  active_runs: number;
  risk: RiskState;
}

export interface ExportRow {
  id: number;
  entity: string;
  format: string;
  status: "pending" | "running" | "done" | "failed";
  rows: number;
  file_name: string | null;
  size_bytes: number | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

/* ------------------------------------------------------------------ */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent("xfox:unauthorized"));
    throw new ApiError(401, "not_authenticated");
  }
  if (!response.ok) {
    let code = `http_${response.status}`;
    try {
      const body = await response.json();
      code = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? code);
    } catch {
      /* keep default */
    }
    throw new ApiError(response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
