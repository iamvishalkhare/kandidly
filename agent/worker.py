"""LiveKit Agents worker entrypoint (SPEC §9.1). Phase-2 (T13) skeleton.

[VERIFY-DOC] The livekit-agents surface — WorkerOptions, cli.run_app, JobContext,
AgentSession, the Deepgram/Cartesia/Silero plugin constructors, room-name job
dispatch, and audio egress — MUST be confirmed against current LiveKit Agents
docs. This file establishes the lifecycle contract; the media pipeline wiring is
filled in during Phase 2. The decision logic already lives in session.py and is
tested independently.
"""

from __future__ import annotations

import structlog

from backend_client import BackendClient
from config import config
from session import InterviewSession

log = structlog.get_logger(__name__)

ROOM_PREFIX = "kndl-"


def _interview_id_from_room(room_name: str) -> str:
    # room_name == 'kndl-{interview_id}' (SPEC §7.9).
    return room_name[len(ROOM_PREFIX):] if room_name.startswith(ROOM_PREFIX) else room_name


async def entrypoint(ctx) -> None:  # ctx: livekit.agents.JobContext  [VERIFY-DOC]
    """Called when the worker accepts a job for a `kndl-*` room."""
    room_name = ctx.room.name
    interview_id = _interview_id_from_room(room_name)
    log.info("agent_job_accepted", room=room_name, interview_id=interview_id)

    backend = BackendClient()
    try:
        session = await InterviewSession.from_bootstrap(interview_id, backend)

        # TODO(Phase-2): build the LiveKit voice pipeline (SPEC §9.2):
        #   from livekit.agents import AgentSession
        #   from livekit.plugins import deepgram, cartesia, silero, anthropic
        #   agent_session = AgentSession(
        #       vad=silero.VAD.load(),
        #       stt=deepgram.STT(model="nova-3", language="en"),
        #       llm=anthropic.LLM(model=...),            # control-prefix system prompt
        #       tts=cartesia.TTS(voice=config.tts_voice),
        #   )
        # For each end-of-turn: assemble context → LLM (streaming) →
        #   session.decide(output, now) → strip @@CTRL, stream remainder to TTS →
        #   session.apply_decision(ctrl) + persist turns via backend.
        # Barge-in, silence ladder (§9.3.4), and injection pub/sub subscription
        # are wired here.

        await session.begin()
        log.info("interview_session_ready", interview_id=interview_id,
                 nodes=len(session.state.nodes))
        # The media loop runs until CLOSE / disconnect, then:
        # await session.close(end_reason="completed")
    finally:
        await backend.aclose()


def main() -> None:
    """`python worker.py start`.

    [VERIFY-DOC] Replace with the documented livekit-agents CLI runner, e.g.:
        from livekit.agents import WorkerOptions, cli
        cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint,
                                  agent_name="kandidly",
                                  # accept only rooms named kndl-*
                                  ))
    """
    log.info("agent_worker_boot", max_concurrent=config.max_concurrent,
             livekit_url=config.livekit_url or "(unset)")
    raise SystemExit(
        "livekit-agents runner not wired yet (Phase 2, T13). "
        "See worker.py [VERIFY-DOC] notes; pure logic is in session.py/control.py/timekeeper.py."
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("start", "dev"):
        main()
    else:
        print("usage: python worker.py start")
