"""Pydantic DTOs — the API contract between the engine and the web console."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from xfox.domain.enums import (
    AccountStatus,
    Aggressiveness,
    ExportEntity,
    ExportFormat,
    ExportStatus,
    JobStatus,
    JobType,
    OutcomeKind,
    Role,
    RunStatus,
    ScheduleKind,
)
from xfox.domain.policies import AppSettings, ScheduleSpec


class ORMModel(BaseModel):
    """Base for models serialized from ORM rows."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth & users
# ---------------------------------------------------------------------------


class SetupRequest(BaseModel):
    """First-run bootstrap: creates the admin account (only when no users exist)."""

    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserPublic(ORMModel):
    id: int
    username: str
    display_name: str | None = None
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)
    role: Role = Role.VIEWER


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# X accounts & proxies
# ---------------------------------------------------------------------------


class AccountStats(ORMModel):
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    items_collected: int = 0
    consecutive_auth_failures: int = 0


class XAccountPublic(ORMModel):
    id: int
    label: str
    notes: str | None = None
    status: AccountStatus
    health_score: int
    proxy_id: int | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    has_cookies: bool
    cookie_updated_at: datetime | None = None
    last_run_at: datetime | None = None
    cooldown_until: datetime | None = None
    created_at: datetime
    updated_at: datetime


class XAccountCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=500)
    proxy_id: int | None = None


class XAccountUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=500)
    proxy_id: int | None = None
    status: AccountStatus | None = None


class CookieUploadRequest(BaseModel):
    """Raw cookie JSON exported via the Cookie-Editor extension (or a Playwright
    storage-state file). Validated and stored inside the account workspace."""

    content: str = Field(min_length=10)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class TimelineTabConfig(BaseModel):
    tab: str = Field(default="Following", description="'Following' or 'For you'")
    max_items: int = Field(default=20, ge=1, le=200)
    max_scrolls: int | None = Field(default=None, ge=1, le=30)


class SearchConfig(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=20)
    max_items_per_keyword: int = Field(default=20, ge=1, le=200)


class NewsConfig(BaseModel):
    detail: bool = False
    max_items: int = Field(default=5, ge=1, le=50)


class MonitorUserConfig(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^@?[A-Za-z0-9_]+$")
    only_new: bool = True
    max_tweets: int = Field(default=10, ge=1, le=100)


class MonitorConfig(BaseModel):
    users: list[MonitorUserConfig] = Field(min_length=1, max_length=50)
    global_max: int = Field(default=100, ge=1, le=1000)


class JobConfig(BaseModel):
    """Type-dependent payload. Exactly the sections required by the job type."""

    search: SearchConfig | None = None
    timeline: list[TimelineTabConfig] | None = None
    news: NewsConfig | None = None
    monitor: MonitorConfig | None = None

    @field_validator("timeline")
    @classmethod
    def _timeline_not_empty(
        cls, value: list[TimelineTabConfig] | None
    ) -> list[TimelineTabConfig] | None:
        if value is not None and len(value) == 0:
            raise ValueError("timeline must contain at least one tab")
        return value


class ScheduleSpecModel(BaseModel):
    kind: ScheduleKind = ScheduleKind.MANUAL
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    daily_at: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")

    def to_spec(self) -> ScheduleSpec:
        return ScheduleSpec(
            kind=self.kind,
            interval_minutes=self.interval_minutes,
            daily_at=self.daily_at,
        )


class JobAntiBanModel(BaseModel):
    aggressiveness: Aggressiveness = Aggressiveness.BALANCED


class JobCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: JobType
    config: JobConfig
    schedule: ScheduleSpecModel = Field(default_factory=ScheduleSpecModel)
    anti_ban: JobAntiBanModel = Field(default_factory=JobAntiBanModel)
    account_id: int | None = None  # pin to a specific X account
    priority: int = Field(default=5, ge=1, le=10)

    @field_validator("config")
    @classmethod
    def _config_matches_type(cls, value: JobConfig, info: ValidationInfo) -> JobConfig:
        job_type = info.data.get("type")
        required = {
            JobType.SEARCH: ("search",),
            JobType.TIMELINE: ("timeline",),
            JobType.NEWS: ("news",),
            JobType.MONITOR: ("monitor",),
            JobType.COMPOSITE: ("search", "timeline", "news", "monitor"),
        }.get(job_type, ())
        if not required:
            return value
        provided = [name for name in required if getattr(value, name) is not None]
        if not provided:
            raise ValueError(f"job type '{job_type}' requires one of: {', '.join(required)}")
        if job_type != JobType.COMPOSITE and len(provided) < len(required):
            raise ValueError(f"job type '{job_type}' requires config.{required[0]}")
        return value

    @field_validator("schedule")
    @classmethod
    def _schedule_complete(cls, value: ScheduleSpecModel) -> ScheduleSpecModel:
        if value.kind == ScheduleKind.INTERVAL and not value.interval_minutes:
            raise ValueError("interval_minutes is required for interval schedules")
        if value.kind == ScheduleKind.DAILY and not value.daily_at:
            raise ValueError("daily_at is required for daily schedules")
        return value


class JobUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: JobConfig | None = None
    schedule: ScheduleSpecModel | None = None
    anti_ban: JobAntiBanModel | None = None
    account_id: int | None = None
    priority: int | None = Field(default=None, ge=1, le=10)


class JobActionRequest(BaseModel):
    action: str = Field(pattern=r"^(run_now|pause|resume)$")


class JobPublic(ORMModel):
    id: int
    name: str
    type: JobType
    config: dict[str, Any]
    schedule: dict[str, Any]
    anti_ban: dict[str, Any]
    account_id: int | None = None
    status: JobStatus
    priority: int
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


class OutcomeInfo(BaseModel):
    kind: OutcomeKind
    message: str | None = None


class RunPublic(ORMModel):
    id: int
    job_id: int
    job_name: str | None = None
    account_id: int | None = None
    account_label: str | None = None
    status: RunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items_new: int = 0
    items_total: int = 0
    outcome: dict[str, Any] | None = None
    duration_ms: int | None = None
    log_excerpt: str | None = None


class RunPage(BaseModel):
    items: list[RunPublic]
    total: int


# ---------------------------------------------------------------------------
# Harvested data (posts & authors)
# ---------------------------------------------------------------------------


class PostStats(BaseModel):
    likes: int = 0
    comments: int = 0
    shares: int = 0
    views: int = 0


class MediaItem(BaseModel):
    type: str
    url: str
    cover_url: str | None = None


class AuthorBrief(BaseModel):
    username: str
    nickname: str | None = None
    avatar_url: str | None = None


class PostPublic(ORMModel):
    id: str
    author: AuthorBrief
    content: str
    description: str | None = None
    url: str | None = None
    source: str
    is_article: bool = False
    stats: PostStats = Field(default_factory=PostStats)
    media: list[MediaItem] = Field(default_factory=list)
    publish_time: datetime | None = None
    crawl_time: datetime | None = None


class PostFilter(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    author: str | None = Field(default=None, max_length=64)
    sources: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_likes: int | None = Field(default=None, ge=0)
    min_views: int | None = Field(default=None, ge=0)
    has_media: bool | None = None
    sort: str = Field(default="publish_time", pattern=r"^(publish_time|likes|views|crawl_time)$")
    order: str = Field(default="desc", pattern=r"^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=5, le=200)


class PostPage(BaseModel):
    items: list[PostPublic]
    total: int
    page: int
    page_size: int


class IngestPost(BaseModel):
    """Normalized X post produced by the ingest mapper (engine → database)."""

    post_id: str
    author_username: str
    author_nickname: str | None = None
    author_avatar: str | None = None
    author_profile: str | None = None
    content: str = ""
    description: str | None = None
    title: str | None = None
    url: str | None = None
    source: str = ""
    is_article: bool = False
    stats: dict[str, int] = Field(default_factory=dict)
    media: list[dict[str, Any]] = Field(default_factory=list)
    publish_time: datetime | None = None
    crawl_time: datetime | None = None
    raw: dict[str, Any] | None = None


class AuthorPublic(ORMModel):
    username: str
    nickname: str | None = None
    avatar_url: str | None = None
    profile_url: str | None = None
    posts_count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class AuthorPage(BaseModel):
    items: list[AuthorPublic]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class EventPublic(ORMModel):
    id: int
    ts: datetime
    type: str
    level: str
    category: str
    message: str
    params: dict[str, Any] | None = None
    account_id: int | None = None
    job_id: int | None = None
    run_id: int | None = None


class EventPage(BaseModel):
    items: list[EventPublic]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Settings & exports
# ---------------------------------------------------------------------------


class AppSettingsUpdate(AppSettings):
    """Full settings replacement (validated against the same defaults)."""


class ProxyPublic(ORMModel):
    id: int
    label: str | None = None
    url: str
    status: str
    latency_ms: int | None = None
    last_check_at: datetime | None = None
    created_at: datetime


class ProxyCreateRequest(BaseModel):
    """``http://user:pass@host:port`` or ``socks5://host:port`` style URLs."""

    label: str | None = Field(default=None, max_length=64)
    url: str = Field(min_length=8, max_length=300, pattern=r"^(https?|socks5h?)://.+")

    @field_validator("url")
    @classmethod
    def _no_credentials_leak(cls, value: str) -> str:
        # Credentials are allowed (proxy auth), just normalized to lowercase scheme.
        return value.strip()


class ProxyUpdateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    url: str | None = Field(
        default=None, min_length=8, max_length=300, pattern=r"^(https?|socks5h?)://.+"
    )
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class ExportCreateRequest(BaseModel):
    entity: ExportEntity
    format: ExportFormat
    filters: PostFilter = Field(default_factory=PostFilter)


class ExportPublic(ORMModel):
    id: int
    entity: str
    format: str
    status: ExportStatus
    rows: int = 0
    file_name: str | None = None
    size_bytes: int | None = None
    error: str | None = None
    created_by: int | None = None
    created_at: datetime
    finished_at: datetime | None = None


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class DailyCount(BaseModel):
    date: str
    count: int


class RiskState(BaseModel):
    level: str
    reasons: list[str] = Field(default_factory=list)
    paused: bool = False
    paused_since: datetime | None = None
    auto_resume_at: datetime | None = None


class OverviewTotals(BaseModel):
    posts: int = 0
    authors: int = 0
    accounts_total: int = 0
    accounts_active: int = 0
    accounts_invalid: int = 0
    jobs_total: int = 0
    jobs_active: int = 0


class OverviewToday(BaseModel):
    runs: int = 0
    successful_runs: int = 0
    items_new: int = 0


class OverviewResponse(BaseModel):
    totals: OverviewTotals
    today: OverviewToday
    risk: RiskState
    engine_running: bool = True
    collection_14d: list[DailyCount] = Field(default_factory=list)
    top_authors: list[AuthorPublic] = Field(default_factory=list)
    recent_runs: list[RunPublic] = Field(default_factory=list)


class SystemStatusResponse(BaseModel):
    version: str
    environment: str
    crawlfox_bin: str
    crawlfox_available: bool
    camoufox_fetched: bool
    database_ok: bool
    data_dir: str
    disk_free_gb: float | None = None
    uptime_seconds: float
    active_runs: int
    risk: RiskState


class MessageResponse(BaseModel):
    message: str
    details: dict[str, Any] | None = None
