"""Account workspaces — one isolated X-CrawlFox home per X account.

X-CrawlFox resolves its configuration from ``.x-crawlfox/`` in the current
working directory when one exists (local mode). Running every invocation with
``cwd`` inside a per-account workspace therefore gives each X account its own
cookies, incremental-crawl state and output — the isolation primitive the whole
multi-account design stands on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xfox.config import settings

COOKIES_FILE = "x_cookies.json"
CONFIG_FILE = "crawl_config.json"
STATE_FILE = "x_crawl_state.json"
FOX_DIR = ".x-crawlfox"
OUTPUT_DIR = "output"


class CookieValidationError(ValueError):
    """Raised when an uploaded cookie document is not usable."""


@dataclass
class Workspace:
    """Filesystem layout for a single X account."""

    account_id: int
    root: Path

    @property
    def fox_dir(self) -> Path:
        return self.root / FOX_DIR

    @property
    def cookies_path(self) -> Path:
        return self.fox_dir / COOKIES_FILE

    @property
    def config_path(self) -> Path:
        return self.fox_dir / CONFIG_FILE

    @property
    def state_path(self) -> Path:
        return self.fox_dir / STATE_FILE

    @property
    def output_dir(self) -> Path:
        return self.root / OUTPUT_DIR


class WorkspaceManager:
    """Creates, inspects and cleans per-account X-CrawlFox workspaces."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.accounts_dir

    def workspace(self, account_id: int) -> Workspace:
        return Workspace(account_id=account_id, root=self.base_dir / str(account_id))

    def ensure(self, account_id: int) -> Workspace:
        ws = self.workspace(account_id)
        ws.fox_dir.mkdir(parents=True, exist_ok=True)
        return ws

    def remove(self, account_id: int) -> None:
        ws = self.workspace(account_id)
        if ws.root.exists():
            import shutil

            shutil.rmtree(ws.root, ignore_errors=True)

    # ------------------------------------------------------------------
    # Cookies
    # ------------------------------------------------------------------

    @staticmethod
    def validate_cookies(content: str) -> dict[str, Any]:
        """Validate a raw cookie JSON document and report its format.

        Accepts either the Cookie-Editor export (a JSON list) or a Playwright
        storage-state object. Returns ``{"format": ..., "cookies": [...]}``.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise CookieValidationError("invalid_json") from exc

        if isinstance(data, list):
            if not data or not isinstance(data[0], dict):
                raise CookieValidationError("empty_or_invalid_cookie_list")
            first = data[0]
            if "expirationDate" in first or "sameSite" in first:
                # Cookie-Editor export format
                for cookie in data:
                    if not {"name", "value", "domain"} <= set(cookie):
                        raise CookieValidationError("missing_cookie_fields")
                return {"format": "cookie_editor", "cookies": data}
            raise CookieValidationError("unrecognized_cookie_list_format")

        if isinstance(data, dict) and isinstance(data.get("cookies"), list):
            # Playwright storage state
            for cookie in data["cookies"]:
                if not {"name", "value", "domain"} <= set(cookie):
                    raise CookieValidationError("missing_cookie_fields")
            return {"format": "playwright", "cookies": data["cookies"]}

        raise CookieValidationError("unrecognized_document")

    @staticmethod
    def _has_x_domain(cookies: list[dict[str, Any]]) -> bool:
        for cookie in cookies:
            domain = str(cookie.get("domain", "")).lower()
            if "x.com" in domain or "twitter.com" in domain:
                return True
        return False

    def install_cookies(self, account_id: int, content: str) -> dict[str, Any]:
        """Validate and persist cookies into the account workspace."""
        report = self.validate_cookies(content)
        if not self._has_x_domain(report["cookies"]):
            raise CookieValidationError("no_x_domain_cookie_found")
        ws = self.ensure(account_id)
        ws.cookies_path.write_text(content.strip(), encoding="utf-8")
        return report

    def has_cookies(self, account_id: int) -> bool:
        return self.workspace(account_id).cookies_path.exists()

    # ------------------------------------------------------------------
    # Crawl config & state
    # ------------------------------------------------------------------

    def write_crawl_config(self, account_id: int, config: dict[str, Any]) -> Path:
        """Write a generated one-shot crawl config for the next invocation."""
        ws = self.ensure(account_id)
        serialized = json.dumps(config, ensure_ascii=False, indent=2)
        ws.config_path.write_text(serialized, encoding="utf-8")
        return ws.config_path

    def clean_output(self, account_id: int) -> None:
        """Remove previous JSONL outputs so each run's file is unambiguous."""
        ws = self.workspace(account_id)
        if ws.output_dir.exists():
            for file in ws.output_dir.glob("*.jsonl"):
                file.unlink(missing_ok=True)

    def read_output_items(
        self, account_id: int, file_name: str | None = None
    ) -> list[dict[str, Any]]:
        """Read harvested items from the run's JSONL output."""
        ws = self.workspace(account_id)
        if not ws.output_dir.exists():
            return []
        files = (
            [ws.output_dir / file_name]
            if file_name
            else sorted(ws.output_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        )
        items: list[dict[str, Any]] = []
        for path in files:
            if not path.exists():
                continue
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    items.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
        return items
