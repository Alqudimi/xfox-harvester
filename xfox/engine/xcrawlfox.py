"""X-CrawlFox adapter — the only module that talks to the harvesting engine.

Responsibilities:
    1. Translate a job configuration into a one-shot ``crawl_config.json``.
    2. Build and execute the ``x-crawlfox x all`` CLI invocation inside the
       account workspace (which provides cookies and incremental state).
    3. Stream every output line to a callback, enforce a hard timeout, and
       kill the whole browser process tree on timeout/cancel.

The CLI contract (commands, flags, log phrases) is pinned against
``x-crawlfox==0.1.2``; the :mod:`xfox.engine.outcomes` classifier owns the
log-to-outcome mapping.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xfox.config import settings
from xfox.domain.enums import JobType
from xfox.domain.policies import CrawlerSettings
from xfox.engine.workspaces import WorkspaceManager


@dataclass
class ExecResult:
    """Raw outcome of one CLI invocation (before classification)."""

    returncode: int
    log_text: str
    timed_out: bool = False
    cancelled: bool = False
    duration_ms: int = 0


LogCallback = Callable[[str], None]


def _timeline_tab_name(tab: str) -> str:
    """Map our short tab ids to X-CrawlFox's expected tab labels."""
    return {"for_you": "For you", "following": "Following"}.get(tab.lower(), tab)


class XCrawlFoxAdapter:
    """Builds and runs X-CrawlFox invocations for one account workspace."""

    def __init__(
        self,
        binary: str | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self.binary = binary or settings.crawlfox_bin
        self.workspaces = workspace_manager or WorkspaceManager()

    # ------------------------------------------------------------------
    # Config generation
    # ------------------------------------------------------------------

    @staticmethod
    def build_crawl_config(
        job_type: JobType,
        job_config: dict[str, Any],
        crawler: CrawlerSettings,
    ) -> dict[str, Any]:
        """Translate our normalized job config into X-CrawlFox's format."""
        x_config: dict[str, Any] = {}
        default_scrolls = crawler.default_max_scrolls

        if search := job_config.get("search"):
            x_config["search"] = [
                {"keyword": keyword, "max_items": int(search.get("max_items_per_keyword", 20))}
                for keyword in search.get("keywords", [])
            ]

        if timeline := job_config.get("timeline"):
            x_config["timeline"] = [
                {
                    "type": _timeline_tab_name(entry.get("tab", "Following")),
                    "max_items": int(entry.get("max_items", 20)),
                    "max_scrolls": int(entry.get("max_scrolls") or default_scrolls),
                }
                for entry in timeline
            ]

        if news := job_config.get("news"):
            x_config["news"] = {
                "enabled": True,
                "detail": bool(news.get("detail", False)),
                "max_items": int(news.get("max_items", 5)),
            }

        if monitor := job_config.get("monitor"):
            x_config["monitor"] = [
                {
                    "username": user.get("username", "").lstrip("@"),
                    "only_new": bool(user.get("only_new", True)),
                    "max_tweets": int(user.get("max_tweets", 10)),
                }
                for user in monitor.get("users", [])
            ]

        if not x_config:
            raise ValueError(f"job type '{job_type}' produced an empty crawl config")

        return {
            "global": {"output_dir": "output", "headless": True},
            "x": x_config,
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def build_command(
        self,
        *,
        config_path: Path,
        headless: bool,
        proxy_url: str | None,
    ) -> list[str]:
        command = [
            self.binary,
            "x",
            "all",
            "--config",
            str(config_path),
            "-o",
            "output",
            "--headless" if headless else "--no-headless",
        ]
        if proxy_url:
            command += ["--proxy", proxy_url]
        return command

    async def execute(
        self,
        *,
        account_id: int,
        config_path: Path,
        headless: bool,
        proxy_url: str | None,
        timeout_minutes: int,
        on_log: LogCallback | None = None,
    ) -> ExecResult:
        """Run one invocation inside the account workspace."""
        workspace = self.workspaces.workspace(account_id)
        command = self.build_command(
            config_path=config_path, headless=headless, proxy_url=proxy_url
        )
        started = time.monotonic()

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(workspace.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # own process group → kill the browser tree
        )

        lines: list[str] = []
        timed_out = False
        cancelled = False

        async def drain() -> None:
            assert process.stdout is not None
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                lines.append(line)
                if on_log is not None:
                    on_log(line)
            await process.wait()

        timeout_seconds = timeout_minutes * 60
        try:
            await asyncio.wait_for(drain(), timeout=timeout_seconds)
        except TimeoutError:
            timed_out = True
            self._kill_tree(process)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=15)
        except asyncio.CancelledError:
            cancelled = True
            self._kill_tree(process)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=15)
            raise

        return ExecResult(
            returncode=process.returncode if process.returncode is not None else -1,
            log_text="\n".join(lines),
            timed_out=timed_out,
            cancelled=cancelled,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    @staticmethod
    def _kill_tree(process: asyncio.subprocess.Process) -> None:
        """Kill the whole process group (Camoufox spawns helper processes)."""
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            with contextlib.suppress(ProcessLookupError):
                process.kill()

    # ------------------------------------------------------------------
    # Environment introspection (system status endpoint)
    # ------------------------------------------------------------------

    @classmethod
    def binary_available(cls, binary: str | None = None) -> bool:
        return shutil.which(binary or settings.crawlfox_bin) is not None

    @classmethod
    def camoufox_fetched(cls) -> bool:
        """True when the Camoufox browser payload has been downloaded."""
        try:
            from camoufox.pkgman import installed_path  # type: ignore[import-untyped]

            installed_path()
            return True
        except Exception:
            return False
