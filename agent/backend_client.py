"""Typed client for the backend /internal API (SPEC §12.3). The agent is the
transcript's writer but the backend is the system of record (SPEC §9.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from config import config


class BackendClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or config.backend_url,
            headers={"X-Service-Token": token or config.service_token},
            timeout=10.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def bootstrap(self, interview_id: str) -> dict[str, Any]:
        r = await self._client.get(f"/internal/interviews/{interview_id}/bootstrap")
        r.raise_for_status()
        return r.json()

    async def create_turn(
        self,
        interview_id: str,
        *,
        seq: int,
        speaker: str,
        text: str,
        started_at: datetime,
        node_id: str | None = None,
        ended_at: datetime | None = None,
        stt_confidence: float | None = None,
        decision: str | None = None,
        meta: dict | None = None,
    ) -> dict:
        payload = {
            "seq": seq, "speaker": speaker, "text": text,
            "started_at": started_at.isoformat(), "node_id": node_id,
            "ended_at": ended_at.isoformat() if ended_at else None,
            "stt_confidence": stt_confidence, "decision": decision, "meta": meta or {},
        }
        r = await self._client.post(f"/internal/interviews/{interview_id}/turns", json=payload)
        r.raise_for_status()
        return r.json()

    async def patch_turn(self, turn_id: str, **fields: Any) -> None:
        if "ended_at" in fields and isinstance(fields["ended_at"], datetime):
            fields["ended_at"] = fields["ended_at"].isoformat()
        r = await self._client.patch(f"/internal/turns/{turn_id}", json=fields)
        r.raise_for_status()

    async def set_status(
        self, interview_id: str, status: str, *, end_reason: str | None = None,
        elapsed_active_seconds: int | None = None,
    ) -> None:
        r = await self._client.post(
            f"/internal/interviews/{interview_id}/status",
            json={"status": status, "end_reason": end_reason,
                  "elapsed_active_seconds": elapsed_active_seconds},
        )
        r.raise_for_status()

    async def heartbeat(self, interview_id: str, elapsed: int, node_id: str | None) -> None:
        await self._client.post(
            f"/internal/interviews/{interview_id}/heartbeat",
            json={"elapsed_active_seconds": elapsed, "current_node_id": node_id},
        )

    async def create_injected_node(
        self, interview_id: str, *, title: str, seed_question: str, position: float, provenance: dict
    ) -> dict:
        r = await self._client.post(
            f"/internal/interviews/{interview_id}/nodes",
            json={"node_type": "injected", "title": title, "seed_question": seed_question,
                  "position": position, "provenance": provenance},
        )
        r.raise_for_status()
        return r.json()

    async def patch_node(self, node_id: str, state: str, skip_reason: str | None = None) -> None:
        await self._client.patch(
            f"/internal/nodes/{node_id}", json={"state": state, "skip_reason": skip_reason}
        )

    async def proctor_events(self, interview_id: str, events: list[dict]) -> None:
        await self._client.post(
            f"/internal/interviews/{interview_id}/proctor-events", json={"events": events}
        )
