"""Outcome classification — turning the X-CrawlFox log stream into decisions.

X-CrawlFox is a friendly CLI: it catches its own exceptions, logs them, and
exits with code 0 either way. The only reliable machine-readable signal is its
log output, so this module maps well-known log phrases (taken verbatim from the
tool's source) onto the engine's :class:`OutcomeKind` vocabulary. Every adverse
outcome directly feeds the anti-ban policy (cooldowns, health, risk gauge).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from xfox.domain.enums import OutcomeKind

_SAVE_LINE = re.compile(r"Save successful! (\d+) items saved to (.+)")
_ERROR_LINE = re.compile(r"\|\s*ERROR\s*\|(.*)")


@dataclass
class RunAnalysis:
    """What the engine learned from one finished invocation."""

    outcome: OutcomeKind
    message: str | None = None
    saved_path: str | None = None
    saved_count: int = 0
    signals: list[str] = field(default_factory=list)


# (signal name, kind, log fragment) — fragments must be lowercase; lines are
# matched case-insensitively and must appear in the message part after the "|".
_SIGNALS: list[tuple[str, OutcomeKind, str]] = [
    ("session_expired", OutcomeKind.AUTH_EXPIRED, "session expiration detected"),
    ("login_hint", OutcomeKind.AUTH_EXPIRED, "please check if you are logged in"),
    ("forced_login", OutcomeKind.AUTH_EXPIRED, "login is forced"),
    ("risk_control", OutcomeKind.RATE_LIMITED, "rate limit/risk control"),
    ("page_abnormal", OutcomeKind.RATE_LIMITED, "x page abnormality detected"),
    ("connection_timeout", OutcomeKind.NETWORK, "connection timeout"),
    ("net_error", OutcomeKind.NETWORK, "net::err"),
    ("browser_error", OutcomeKind.BROWSER, "browser automation error"),
    ("browser_closed", OutcomeKind.BROWSER, "browser closed"),
    ("target_closed", OutcomeKind.BROWSER, "target closed"),
    ("page_closed", OutcomeKind.BROWSER, "page is closed"),
    ("empty_result", OutcomeKind.EMPTY, "failed to scrape"),
    ("no_new_tweets", OutcomeKind.EMPTY, "no new tweets found"),
    ("no_data_scraped", OutcomeKind.EMPTY, "no data scraped"),
    ("unknown_error", OutcomeKind.UNKNOWN_ERROR, "an unknown error occurred"),
]


def _message_part(line: str) -> str:
    """Extract the human message from a loguru-formatted line (after last '|')."""
    parts = line.split("|")
    return parts[-1] if len(parts) > 1 else line


# Adverse outcomes in resolution priority (most safety-critical first).
_PRIORITY_KINDS = (
    OutcomeKind.AUTH_EXPIRED,
    OutcomeKind.RATE_LIMITED,
    OutcomeKind.BROWSER,
    OutcomeKind.NETWORK,
)


def _resolve_outcome(
    detected: list[tuple[str, OutcomeKind]],
    *,
    items_collected: int,
    saved_count: int,
    timed_out: bool,
    cancelled: bool,
) -> OutcomeKind:
    if cancelled:
        return OutcomeKind.CANCELLED
    if timed_out:
        return OutcomeKind.TIMEOUT
    kinds = {kind for _, kind in detected}
    for kind in _PRIORITY_KINDS:
        if kind in kinds:
            return kind
    if items_collected > 0 or saved_count > 0:
        return OutcomeKind.SUCCESS
    if OutcomeKind.EMPTY in kinds:
        return OutcomeKind.EMPTY
    if OutcomeKind.UNKNOWN_ERROR in kinds:
        return OutcomeKind.UNKNOWN_ERROR
    return OutcomeKind.EMPTY


def analyze_log(
    log_text: str,
    *,
    timed_out: bool = False,
    cancelled: bool = False,
    items_collected: int = 0,
) -> RunAnalysis:
    """Classify a completed X-CrawlFox invocation from its captured log."""
    detected: list[tuple[str, OutcomeKind]] = []
    saved_path: str | None = None
    saved_count = 0
    last_error: str | None = None

    for line in log_text.splitlines():
        message = _message_part(line).strip()
        lowered = message.lower()

        match = _SAVE_LINE.search(message)
        if match:
            saved_count = int(match.group(1))
            saved_path = match.group(2).strip()

        error_match = _ERROR_LINE.search(line)
        if error_match:
            last_error = error_match.group(1).strip()

        for signal_name, kind, fragment in _SIGNALS:
            if fragment in lowered:
                detected.append((signal_name, kind))
                break  # one signal per line is enough

    signals = [name for name, _ in detected]

    return RunAnalysis(
        outcome=_resolve_outcome(
            detected,
            items_collected=items_collected,
            saved_count=saved_count,
            timed_out=timed_out,
            cancelled=cancelled,
        ),
        message=last_error,
        saved_path=saved_path,
        saved_count=saved_count,
        signals=signals,
    )
