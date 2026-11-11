"""Central enumeration vocabulary.

Every state machine in the system uses the enums defined here, so the web
console, the engine, and the database always agree on terminology.
"""

from enum import StrEnum


class Role(StrEnum):
    """Console user roles."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(StrEnum):
    """Fine-grained capabilities checked by the API layer."""

    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"

    ACCOUNTS_READ = "accounts:read"
    ACCOUNTS_MANAGE = "accounts:manage"

    PROXIES_READ = "proxies:read"
    PROXIES_MANAGE = "proxies:manage"

    JOBS_READ = "jobs:read"
    JOBS_MANAGE = "jobs:manage"

    DATA_READ = "data:read"
    DATA_EXPORT = "data:export"

    EVENTS_READ = "events:read"

    SETTINGS_READ = "settings:read"
    SETTINGS_MANAGE = "settings:manage"

    SYSTEM_READ = "system:read"
    SYSTEM_MANAGE = "system:manage"


class JobType(StrEnum):
    """Harvest job types, mapped 1:1 to X-CrawlFox capabilities."""

    SEARCH = "search"          # keyword search on X (humanized typing)
    TIMELINE = "timeline"      # home feed: For you / Following
    NEWS = "news"              # "Today's News" sidebar (+ optional deep detail)
    MONITOR = "monitor"        # incremental watch of specific accounts
    COMPOSITE = "composite"    # several of the above in one browser session


class JobStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class RunStatus(StrEnum):
    """Lifecycle of a single job execution (one X-CrawlFox invocation)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"        # finished, produced items
    EMPTY = "empty"            # finished cleanly, zero new items
    FAILED = "failed"          # engine or page failure
    TIMEOUT = "timeout"        # killed after run_timeout_minutes
    CANCELLED = "cancelled"    # stopped by a user
    SKIPPED = "skipped"        # never started (no eligible account, etc.)


class AccountStatus(StrEnum):
    """Health state of an X account (workspace)."""

    ACTIVE = "active"
    COOLDOWN = "cooldown"      # temporarily resting (anti-ban)
    DISABLED = "disabled"      # switched off by a user
    INVALID = "invalid"        # cookies rejected by X (needs re-login)


class RiskLevel(StrEnum):
    """Global engine risk gauge."""

    GREEN = "green"
    YELLOW = "yellow"          # elevated friction — engine slows down
    RED = "red"                # critical — engine pauses (manual/auto resume)


class OutcomeKind(StrEnum):
    """Classification of a finished X-CrawlFox invocation.

    Derived from the tool's log stream — see ``xfox.engine.outcomes``.
    """

    SUCCESS = "success"
    EMPTY = "empty"
    RATE_LIMITED = "rate_limited"    # X risk-control / "Something went wrong"
    AUTH_EXPIRED = "auth_expired"    # session expired, forced login redirect
    NETWORK = "network"              # timeouts, DNS, proxy failures
    BROWSER = "browser"              # Camoufox/Playwright failures
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"          # no eligible account / pre-flight failure
    UNKNOWN_ERROR = "unknown_error"


class Aggressiveness(StrEnum):
    """Per-job pacing presets on top of the global anti-ban policy."""

    CAUTIOUS = "cautious"    # ~1.6x gaps, half the daily caps
    BALANCED = "balanced"    # global defaults
    FAST = "fast"            # ~0.6x gaps, 1.5x caps (higher risk)


class ScheduleKind(StrEnum):
    MANUAL = "manual"        # only runs when triggered explicitly
    INTERVAL = "interval"    # every N minutes (with jitter)
    DAILY = "daily"          # once a day at HH:MM


class ExportFormat(StrEnum):
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


class ExportEntity(StrEnum):
    POSTS = "posts"
    AUTHORS = "authors"


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class EventLevel(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class EventCategory(StrEnum):
    SYSTEM = "system"
    SECURITY = "security"
    ACCOUNT = "account"
    JOB = "job"
    RUN = "run"
    DATA = "data"
    RISK = "risk"
    EXPORT = "export"


class EventType(StrEnum):
    """Stable event identifiers — the web console localizes them (ar/en)."""

    # system
    SERVER_STARTED = "server_started"
    SERVER_STOPPED = "server_stopped"

    # security
    USER_CREATED = "user_created"
    USER_LOGIN = "user_login"
    USER_LOGIN_FAILED = "user_login_failed"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    PASSWORD_CHANGED = "password_changed"

    # accounts
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_UPDATED = "account_updated"
    ACCOUNT_DELETED = "account_deleted"
    COOKIES_UPDATED = "cookies_updated"
    COOKIES_REJECTED = "cookies_rejected"
    ACCOUNT_TESTED = "account_tested"
    ACCOUNT_COOLDOWN = "account_cooldown"
    ACCOUNT_RECOVERED = "account_recovered"
    ACCOUNT_INVALIDATED = "account_invalidated"
    ACCOUNT_DISABLED_BY_HEALTH = "account_disabled_by_health"

    # proxies
    PROXY_CREATED = "proxy_created"
    PROXY_UPDATED = "proxy_updated"
    PROXY_DELETED = "proxy_deleted"
    PROXY_CHECKED = "proxy_checked"

    # jobs
    JOB_CREATED = "job_created"
    JOB_UPDATED = "job_updated"
    JOB_DELETED = "job_deleted"
    JOB_PAUSED = "job_paused"
    JOB_RESUMED = "job_resumed"
    JOB_TRIGGERED = "job_triggered"

    # runs
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_LOG = "run_log"
    RUN_CANCELLED = "run_cancelled"
    RUN_BACKOFF = "run_backoff"

    # data
    ITEMS_INGESTED = "items_ingested"

    # risk
    RISK_LEVEL_CHANGED = "risk_level_changed"
    ENGINE_PAUSED = "engine_paused"
    ENGINE_RESUMED = "engine_resumed"

    # exports
    EXPORT_CREATED = "export_created"
    EXPORT_FINISHED = "export_finished"
    EXPORT_FAILED = "export_failed"

    # settings
    SETTINGS_UPDATED = "settings_updated"

    # maintenance
    MAINTENANCE_PURGE = "maintenance_purge"
    DATA_PURGED = "data_purged"
