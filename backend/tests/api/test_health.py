"""/healthz contract — the deploy pipeline greps status and the deployed sha."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_healthz_reports_status_and_sha(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sha"]  # "unknown" outside a deploy; never empty
