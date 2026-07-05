"""InterviewSession orchestration (SPEC §9). This wires the pure, tested modules
(control, timekeeper, datamsg) and the backend client into the per-turn loop.

The media plane (LiveKit AgentSession, Deepgram STT, Cartesia TTS, VAD/turn
detection) is Phase-2 integration (T13) and marked [VERIFY-DOC] — those calls
belong in worker.py's entrypoint using livekit-agents. The turn-decision logic
here is provider-agnostic and unit-testable in isolation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from backend_client import BackendClient
from control import Ctrl, OverrideContext, apply_overrides, default_ctrl, parse_ctrl, split_output
from timekeeper import Timekeeper

log = structlog.get_logger(__name__)


@dataclass
class NodeState:
    id: str
    node_type: str
    title: str
    seed_question: str
    max_followups: int
    state: str = "pending"
    followups_used: int = 0


@dataclass
class SessionState:
    interview_id: str
    room_name: str
    nodes: list[NodeState]
    timekeeper: Timekeeper
    seq: int = 0
    current_index: int = 0
    pending_injection_node_id: str | None = None
    summary: str = ""
    recent_turns: list[tuple[str, str]] = field(default_factory=list)  # (speaker, text)

    @property
    def current_node(self) -> NodeState | None:
        return self.nodes[self.current_index] if 0 <= self.current_index < len(self.nodes) else None

    def remaining_node_ids(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.nodes[self.current_index + 1:] if n.state == "pending")


class InterviewSession:
    """Owns one interview's control flow. Constructed from the backend bootstrap."""

    def __init__(self, state: SessionState, backend: BackendClient) -> None:
        self.state = state
        self.backend = backend

    @classmethod
    async def from_bootstrap(cls, interview_id: str, backend: BackendClient) -> "InterviewSession":
        data = await backend.bootstrap(interview_id)
        cfg = data.get("config") or {}
        tk = Timekeeper(
            max_duration_seconds=cfg.get("max_duration_seconds", 1800),
            wrap_trigger_seconds=cfg.get("wrap_trigger_seconds", 180),
            elapsed_active_seconds=data["interview"]["elapsed_active_seconds"],
        )
        nodes = [
            NodeState(
                id=n["id"], node_type=n["node_type"], title=n["title"],
                seed_question=n["seed_question"], max_followups=n["max_followups"], state=n["state"],
            )
            for n in data["nodes"]
        ]
        # Resume at the first non-done node (crash-recovery, SPEC §9.4).
        current = next((i for i, n in enumerate(nodes) if n.state in ("pending", "active")), 0)
        st = SessionState(
            interview_id=interview_id, room_name=data["interview"]["room_name"],
            nodes=nodes, timekeeper=tk, current_index=current,
        )
        return cls(st, backend)

    # -- decision core (pure-ish; the unit-testable heart of the loop) -------
    def decide(self, llm_output: str, now: float) -> tuple[Ctrl, str, tuple[str, ...]]:
        """Parse the LLM output, apply enforcement overrides (SPEC §8.7), and
        return (final_ctrl, spoken_text, overrides_applied). No I/O."""
        first_line, spoken = split_output(llm_output)
        node = self.state.current_node
        current_id = node.id if node else ""
        ctrl = parse_ctrl(first_line)
        if ctrl is None:
            ctrl = default_ctrl(current_id)  # caller logs ctrl_parse_error

        ctx = OverrideContext(
            current_node_id=current_id,
            followups_used=node.followups_used if node else 0,
            max_followups=node.max_followups if node else 0,
            wrap_phase=self.state.timekeeper.in_wrap_or_later(now),
            injection_node_id=self.state.pending_injection_node_id,
            remaining_node_ids=self.state.remaining_node_ids(),
        )
        result = apply_overrides(ctrl, ctx)
        return result.ctrl, spoken, result.overrides_applied

    def apply_decision(self, ctrl: Ctrl) -> None:
        """Mutate session bookkeeping after a decision is finalized."""
        node = self.state.current_node
        if node is None:
            return
        if ctrl.d == "PROBE":
            node.followups_used += 1
        if ctrl.d in ("ADVANCE", "WRAP") or ctrl.end:
            node.state = "done"
            self.state.pending_injection_node_id = None
            if self.state.current_index < len(self.state.nodes) - 1:
                self.state.current_index += 1
                if self.state.current_node:
                    self.state.current_node.state = "active"

    # -- persistence ---------------------------------------------------------
    async def persist_candidate_turn(self, text: str, stt_confidence: float | None) -> dict:
        self.state.seq += 1
        node = self.state.current_node
        return await self.backend.create_turn(
            self.state.interview_id, seq=self.state.seq, speaker="candidate", text=text,
            started_at=datetime.now(timezone.utc), node_id=node.id if node else None,
            ended_at=datetime.now(timezone.utc), stt_confidence=stt_confidence,
        )

    async def persist_kandidly_turn(self, ctrl: Ctrl, text: str, latency_ms: int) -> dict:
        self.state.seq += 1
        node = self.state.current_node
        return await self.backend.create_turn(
            self.state.interview_id, seq=self.state.seq, speaker="kandidly", text=text,
            started_at=datetime.now(timezone.utc), node_id=node.id if node else None,
            decision=ctrl.d, meta={"latency_ms": latency_ms, "raw_ctrl": ctrl.__dict__},
        )

    # -- lifecycle (media plumbing lives in worker.py) -----------------------
    async def begin(self) -> None:
        """Candidate joined → status live, start clock, egress. [VERIFY-DOC egress]."""
        self.state.timekeeper.mark_live(time.monotonic())
        await self.backend.set_status(self.state.interview_id, "live")
        # TODO(Phase-2): start LiveKit audio egress → kandidly-recordings/{id}/audio.ogg.

    async def close(self, end_reason: str) -> None:
        now = time.monotonic()
        self.state.timekeeper.mark_paused(now)
        await self.backend.set_status(
            self.state.interview_id, "ended", end_reason=end_reason,
            elapsed_active_seconds=self.state.timekeeper.elapsed(now),
        )
