"""End-to-end API integration tests against the test database."""

import json
from datetime import UTC


class TestAuthFlow:
    async def test_bootstrap_status(self, client):
        response = await client.get("/api/auth/bootstrap-status")
        assert response.status_code == 200
        assert "initialized" in response.json()

    async def test_setup_rejected_twice(self, admin_client):
        response = await admin_client.post(
            "/api/auth/setup", json={"username": "other", "password": "OtherPass123!"}
        )
        assert response.status_code == 409

    async def test_login_rejects_bad_credentials(self, admin_client):
        await admin_client.post("/api/auth/logout")
        response = await admin_client.post(
            "/api/auth/login", json={"username": "ghost", "password": "WrongPass123!"}
        )
        assert response.status_code == 401

    async def test_me_requires_auth(self, client):
        response = await client.get("/api/auth/me")
        assert response.status_code == 401


class TestRbac:
    async def test_viewer_cannot_create_jobs(self, viewer_client):
        response = await viewer_client.post(
            "/api/jobs",
            json={
                "name": "v",
                "type": "search",
                "config": {"search": {"keywords": ["a"]}},
                "schedule": {"kind": "manual"},
            },
        )
        assert response.status_code == 403

    async def test_viewer_can_read_jobs(self, viewer_client):
        response = await viewer_client.get("/api/jobs")
        assert response.status_code == 200

    async def test_viewer_cannot_manage_users(self, viewer_client):
        response = await viewer_client.get("/api/users")
        assert response.status_code == 403

    async def test_operator_can_manage_accounts(self, admin_client):
        response = await admin_client.post(
            "/api/accounts", json={"label": "ops-account"}
        )
        assert response.status_code == 201


class TestAccountsAndJobs:
    async def test_full_lifecycle(self, admin_client):
        # 1) create an account
        response = await admin_client.post("/api/accounts", json={"label": "lifecycle"})
        assert response.status_code == 201
        account_id = response.json()["id"]

        # 2) reject bad cookies, accept good ones
        bad = await admin_client.post(
            f"/api/accounts/{account_id}/cookies", json={"content": "[{\"name\":\"a\"}]"}
        )
        assert bad.status_code == 400

        cookies = json.dumps(
            [
                {
                    "name": "auth_token",
                    "value": "x",
                    "domain": ".x.com",
                    "path": "/",
                    "expirationDate": 1893456000,
                }
            ]
        )
        good = await admin_client.post(
            f"/api/accounts/{account_id}/cookies", json={"content": cookies}
        )
        assert good.status_code == 200
        assert good.json()["cookie_count"] == 1

        # 3) create a monitor job pinned to the account
        response = await admin_client.post(
            "/api/jobs",
            json={
                "name": "مراقبة الاختبار",
                "type": "monitor",
                "config": {
                    "monitor": {
                        "users": [{"username": "elonmusk", "only_new": True, "max_tweets": 5}],
                        "global_max": 50,
                    }
                },
                "schedule": {"kind": "interval", "interval_minutes": 60},
                "anti_ban": {"aggressiveness": "cautious"},
                "account_id": account_id,
                "priority": 8,
            },
        )
        assert response.status_code == 201
        job = response.json()
        assert job["type"] == "monitor"
        assert job["account_id"] == account_id
        assert job["next_run_at"] is not None  # interval jobs schedule immediately
        job_id = job["id"]

        # 4) invalid config rejected (search job without keywords)
        invalid = await admin_client.post(
            "/api/jobs",
            json={
                "name": "bad",
                "type": "search",
                "config": {"search": None},
                "schedule": {"kind": "manual"},
            },
        )
        assert invalid.status_code == 422

        # 5) trigger the job manually
        triggered = await admin_client.post(f"/api/jobs/{job_id}/action", json={"action": "run_now"})
        assert triggered.status_code == 200
        run_id = triggered.json()["details"]["run_id"]

        # 6) run history visible
        runs = await admin_client.get(f"/api/jobs/{job_id}/runs")
        assert runs.status_code == 200
        assert any(run["id"] == run_id for run in runs.json()["items"])

        # 7) pause and resume
        await admin_client.post(f"/api/jobs/{job_id}/action", json={"action": "pause"})
        status = await admin_client.get(f"/api/jobs/{job_id}")
        assert status.json()["status"] == "paused"
        await admin_client.post(f"/api/jobs/{job_id}/action", json={"action": "resume"})
        status = await admin_client.get(f"/api/jobs/{job_id}")
        assert status.json()["status"] == "active"

        # 8) update the job
        patched = await admin_client.patch(
            f"/api/jobs/{job_id}", json={"name": "مراقبة محدثة"}
        )
        assert patched.json()["name"] == "مراقبة محدثة"

        # 9) delete
        deleted = await admin_client.delete(f"/api/jobs/{job_id}")
        assert deleted.status_code == 200
        assert (await admin_client.get(f"/api/jobs/{job_id}")).status_code == 404

    async def test_account_test_without_cookies_fails_cleanly(self, admin_client):
        response = await admin_client.post("/api/accounts", json={"label": "no-cookies"})
        account_id = response.json()["id"]
        tested = await admin_client.post(f"/api/accounts/{account_id}/test")
        assert tested.status_code == 400
        assert tested.json()["detail"] == "no_cookies_installed"


class TestSettingsAndSystem:
    async def test_settings_roundtrip(self, admin_client):
        current = await admin_client.get("/api/settings")
        assert current.status_code == 200
        payload = current.json()
        payload["anti_ban"]["min_run_gap_minutes"] = 45
        updated = await admin_client.put("/api/settings", json=payload)
        assert updated.status_code == 200
        assert updated.json()["anti_ban"]["min_run_gap_minutes"] == 45

        # restore
        payload["anti_ban"]["min_run_gap_minutes"] = 30
        await admin_client.put("/api/settings", json=payload)

    async def test_settings_validation_rejects_bad_values(self, admin_client):
        current = (await admin_client.get("/api/settings")).json()
        current["anti_ban"]["max_concurrent_runs"] = 99
        response = await admin_client.put("/api/settings", json=current)
        assert response.status_code == 422

    async def test_overview_shape(self, admin_client):
        response = await admin_client.get("/api/system/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["risk"]["level"] in {"green", "yellow", "red"}
        assert "totals" in body and "collection_14d" in body

    async def test_system_status(self, admin_client):
        response = await admin_client.get("/api/system/status")
        assert response.status_code == 200
        body = response.json()
        assert body["database_ok"] is True
        assert body["version"] == "1.0.0"

    async def test_viewer_cannot_save_settings(self, viewer_client):
        response = await viewer_client.get("/api/settings")
        assert response.status_code == 200
        response = await viewer_client.put("/api/settings", json=response.json())
        assert response.status_code == 403


class TestIngestionEndpoint:
    @staticmethod
    async def _ingest_samples(db_session, count: int = 7) -> None:
        from datetime import datetime

        from xfox.db.repo.posts import ingest_posts
        from xfox.domain.schemas import IngestPost

        items = [
            IngestPost(
                post_id=f"post-{index}",
                author_username=f"user{index}",
                author_nickname=f"مستخدم {index}",
                content=f"محتوى تجريبي {index} — ذكاء اصطناعي",
                source="search_simulated",
                stats={"likes": index * 10, "views": index * 100},
                publish_time=datetime.now(tz=UTC),
                crawl_time=datetime.now(tz=UTC),
            )
            for index in range(1, count + 1)
        ]
        await ingest_posts(db_session, items)
        await db_session.commit()

    async def test_ingest_and_query_posts(self, admin_client, db_session):
        await self._ingest_samples(db_session, 7)

        # re-ingest is idempotent
        from datetime import datetime

        from xfox.db.repo.posts import ingest_posts
        from xfox.domain.schemas import IngestPost

        again = [
            IngestPost(
                post_id="post-1",
                author_username="user1",
                content="محتوى تجريبي 1",
                source="search_simulated",
                publish_time=datetime.now(tz=UTC),
                crawl_time=datetime.now(tz=UTC),
            )
        ]
        inserted_again, _ = await ingest_posts(db_session, again)
        assert inserted_again == 0
        await db_session.commit()

        posts = await admin_client.get("/api/data/posts?q=ذكاء&page_size=10")
        assert posts.status_code == 200
        body = posts.json()
        assert body["total"] >= 7

        filtered = await admin_client.get("/api/data/posts?min_likes=30&sort=likes&order=desc")
        body = filtered.json()
        assert all(post["stats"]["likes"] >= 30 for post in body["items"])

        authors = await admin_client.get("/api/data/authors")
        assert authors.json()["total"] >= 7

        sources = await admin_client.get("/api/data/sources")
        assert "search_simulated" in sources.json()

    async def test_export_flow(self, admin_client, db_session):
        await self._ingest_samples(db_session, 7)

        created = await admin_client.post(
            "/api/exports",
            json={"entity": "posts", "format": "csv", "filters": {"page": 1, "page_size": 25}},
        )
        assert created.status_code == 201
        export_id = created.json()["id"]

        import asyncio

        for _ in range(20):
            row = (await admin_client.get(f"/api/exports/{export_id}")).json()
            if row["status"] in {"done", "failed"}:
                break
            await asyncio.sleep(0.25)

        assert row["status"] == "done"
        assert row["rows"] >= 7

        download = await admin_client.get(f"/api/exports/{export_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("text/csv")


class TestUsersManagement:
    async def test_create_update_delete_user(self, admin_client):
        created = await admin_client.post(
            "/api/users",
            json={"username": "temp_operator", "password": "TempPass123!", "role": "operator"},
        )
        assert created.status_code == 201
        user_id = created.json()["id"]

        promoted = await admin_client.patch(f"/api/users/{user_id}", json={"role": "viewer"})
        assert promoted.json()["role"] == "viewer"

        deactivated = await admin_client.patch(f"/api/users/{user_id}", json={"is_active": False})
        assert deactivated.json()["is_active"] is False

        deleted = await admin_client.delete(f"/api/users/{user_id}")
        assert deleted.status_code == 200

    async def test_duplicate_username_rejected(self, admin_client):
        created = await admin_client.post(
            "/api/users", json={"username": "temp_operator", "password": "TempPass123!"}
        )
        duplicate = await admin_client.post(
            "/api/users", json={"username": "temp_operator", "password": "OtherPass123!"}
        )
        assert duplicate.status_code == 409
        await admin_client.delete(f"/api/users/{created.json()['id']}")
