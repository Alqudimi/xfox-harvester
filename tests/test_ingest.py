"""Ingest-mapper and workspace tests."""

import json

import pytest

from xfox.engine.ingest import map_items
from xfox.engine.workspaces import CookieValidationError, WorkspaceManager


def _item(**overrides):
    base = {
        "id": "1912345678901234567",
        "platform": "x",
        "url": "https://x.com/user/status/1912345678901234567",
        "content": "مرحبا بالعالم",
        "description": None,
        "author": {
            "nickname": "مستخدم",
            "username": "@SomeUser",
            "profile_url": "https://x.com/SomeUser",
        },
        "media": [{"type": "image", "url": "https://pbs.twimg.com/media/abc.jpg"}],
        "stats": {"likes": 1200, "comments": 34, "shares": 56, "views": "45K"},
        "publish_time": "2026-04-19T10:00:00Z",
        "crawl_time": "2026-04-19T12:00:00Z",
        "source": "search_simulated",
        "is_article": False,
    }
    base.update(overrides)
    return base


class TestMapItems:
    def test_maps_regular_item(self):
        posts, skipped = map_items([_item()])
        assert skipped == 0
        assert len(posts) == 1
        post = posts[0]
        assert post.post_id == "1912345678901234567"
        assert post.author_username == "someuser"
        assert post.stats["likes"] == 1200
        assert post.publish_time is not None and post.publish_time.year == 2026
        assert post.media[0]["type"] == "image"

    def test_skips_unknown_ids(self):
        posts, skipped = map_items([_item(id="unknown_4242")])
        assert posts == []
        assert skipped == 1

    def test_skips_items_without_author(self):
        posts, skipped = map_items([_item(author={"nickname": "x", "username": ""})])
        assert skipped == 1

    def test_views_shorthand_becomes_zero(self):
        posts, _ = map_items([_item()])
        assert posts[0].stats["views"] == 0  # "45K" is not an int → 0 (X-CrawlFox sends real ints)

    def test_handles_missing_times(self):
        posts, _ = map_items([_item(publish_time=None, crawl_time=None)])
        assert posts[0].publish_time is None

    def test_batch_mixed(self):
        items = [_item(), _item(id="unknown_1"), _item(id="20"), "not-a-dict"]
        posts, skipped = map_items(items)
        assert len(posts) == 2
        assert skipped == 2


class TestWorkspaceCookies:
    manager = WorkspaceManager(base_dir=__import__("pathlib").Path("/tmp/xfox-test-data/accounts"))

    def test_rejects_invalid_json(self):
        with pytest.raises(CookieValidationError):
            self.manager.validate_cookies("{not json")

    def test_rejects_wrong_format(self):
        with pytest.raises(CookieValidationError):
            self.manager.validate_cookies(json.dumps([{"foo": "bar"}]))

    def test_accepts_cookie_editor_format(self):
        content = json.dumps(
            [
                {
                    "name": "auth_token",
                    "value": "abc",
                    "domain": ".x.com",
                    "path": "/",
                    "expirationDate": 1893456000,
                    "sameSite": "no_restriction",
                }
            ]
        )
        report = self.manager.validate_cookies(content)
        assert report["format"] == "cookie_editor"
        assert len(report["cookies"]) == 1

    def test_accepts_playwright_storage_state(self):
        content = json.dumps(
            {"cookies": [{"name": "ct0", "value": "x", "domain": ".x.com", "path": "/"}], "origins": []}
        )
        report = self.manager.validate_cookies(content)
        assert report["format"] == "playwright"

    def test_install_requires_x_domain(self):
        content = json.dumps(
            [{"name": "a", "value": "b", "domain": ".example.com", "path": "/", "expirationDate": 1}]
        )
        with pytest.raises(CookieValidationError) as error:
            self.manager.install_cookies(999, content)
        assert "no_x_domain" in str(error.value)

    def test_install_and_read_roundtrip(self):
        content = json.dumps(
            [
                {
                    "name": "auth_token",
                    "value": "secret",
                    "domain": ".x.com",
                    "path": "/",
                    "expirationDate": 1893456000,
                }
            ]
        )
        report = self.manager.install_cookies(1001, content)
        assert report["format"] == "cookie_editor"
        assert self.manager.has_cookies(1001)

        ws = self.manager.workspace(1001)
        ws.output_dir.mkdir(parents=True, exist_ok=True)
        (ws.output_dir / "all_crawled_results_20260419_120000.jsonl").write_text(
            json.dumps(_item(), ensure_ascii=False) + "\n", encoding="utf-8"
        )
        items = self.manager.read_output_items(1001)
        assert len(items) == 1
        assert items[0]["content"] == "مرحبا بالعالم"

        self.manager.remove(1001)
        assert not self.manager.has_cookies(1001)
