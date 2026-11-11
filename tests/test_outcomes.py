"""Outcome-classification tests over real X-CrawlFox log phrasing."""

from xfox.domain.enums import OutcomeKind
from xfox.engine.outcomes import analyze_log


def test_successful_run_with_save_line():
    log = (
        "2026-04-19 12:00:01.000 | INFO | x_crawlfox.cli.x_commands:all:261 - Search keyword: AI (max_items=20)...\n"
        "2026-04-19 12:00:40.000 | INFO | x_crawlfox.cli.utils:save_items:36 - Save successful! 20 items saved to output/all_crawled_results_20260419_120040.jsonl"
    )
    analysis = analyze_log(log)
    assert analysis.outcome == OutcomeKind.SUCCESS
    assert analysis.saved_count == 20
    assert analysis.saved_path.endswith(".jsonl")


def test_session_expired_detected():
    log = "2026-04-19 12:00:05.000 | ERROR | x_crawlfox.core.base_scraper:_check_and_retry_error:47 - Session expiration detected, login is forced."
    assert analyze_log(log).outcome == OutcomeKind.AUTH_EXPIRED


def test_login_hint_detected():
    log = "2026-04-19 12:00:05.000 | WARNING | x_crawlfox.cli.x_commands:timeline:71 - Failed to scrape any tweets. Please check if you are logged in or if the page loaded normally."
    assert analyze_log(log).outcome == OutcomeKind.AUTH_EXPIRED


def test_risk_control_detected():
    log = (
        "2026-04-19 12:00:05.000 | WARNING | x_crawlfox.core.base_scraper:_check_and_retry_error:32 - X page abnormality detected (rate limit/risk control), recovery attempt 1...\n"
        "2026-04-19 12:00:20.000 | WARNING | x_crawlfox.cli.x_commands:all:325 - Full crawl task finished, no data scraped."
    )
    analysis = analyze_log(log)
    assert analysis.outcome == OutcomeKind.RATE_LIMITED


def test_browser_error_detected():
    log = "2026-04-19 12:00:05.000 | ERROR | x_crawlfox.cli.utils:handle_error:13 - Browser automation error: executable doesn't exist"
    assert analyze_log(log).outcome == OutcomeKind.BROWSER


def test_network_timeout_detected():
    log = "2026-04-19 12:00:05.000 | ERROR | x_crawlfox.cli.utils:handle_error:10 - Connection timeout! Please check your network environment (VPN?) or proxy settings (--proxy)."
    assert analyze_log(log).outcome == OutcomeKind.NETWORK


def test_empty_run_without_items():
    log = (
        "2026-04-19 12:00:01.000 | INFO | x_crawlfox.cli.x_commands:all:261 - Preparing to scrape Following timeline...\n"
        "2026-04-19 12:00:20.000 | WARNING | x_crawlfox.cli.x_commands:monitor:182 - Monitor run finished. No new tweets found."
    )
    assert analyze_log(log).outcome == OutcomeKind.EMPTY


def test_items_collected_overrides_empty_signal():
    log = "2026-04-19 12:00:20.000 | WARNING | x_crawlfox.cli.x_commands:all:325 - Full crawl task finished, no data scraped."
    analysis = analyze_log(log, items_collected=7)
    assert analysis.outcome == OutcomeKind.SUCCESS


def test_timeout_and_cancelled_flags_win():
    assert analyze_log("anything", timed_out=True).outcome == OutcomeKind.TIMEOUT
    assert analyze_log("anything", cancelled=True).outcome == OutcomeKind.CANCELLED


def test_auth_priority_over_rate_limit():
    log = (
        "2026-04-19 12:00:05.000 | WARNING | x_crawlfox.core.base_scraper:_check_and_retry_error:32 - X page abnormality detected (rate limit/risk control), recovery attempt 1...\n"
        "2026-04-19 12:00:25.000 | ERROR | x_crawlfox.core.base_scraper:_check_and_retry_error:47 - Session expiration detected, login is forced."
    )
    assert analyze_log(log).outcome == OutcomeKind.AUTH_EXPIRED
