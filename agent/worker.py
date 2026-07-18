"""Kandidly LiveKit Agents worker (SPEC §9) — the realtime interview brain.

Built on livekit-agents 1.6.x using LiveKit Cloud *inference* for STT/LLM/TTS
(one credential set — no separate Deepgram/Cartesia/Anthropic accounts). The
worker auto-dispatches to `kndl-*` rooms a candidate creates, bootstraps the
interview from the backend, conducts a spoken screening, and writes the
transcript + lifecycle back through the /internal API so the DB is the system
of record. It also mirrors captions/timer/state to the candidate's browser over
the `kandidly` data channel (see datamsg.py / web interviewChannel.ts).

Models are LiveKit-inference IDs and are overridable via env
(KANDIDLY_INFERENCE_STT / _LLM / _TTS / _TTS_VOICE) — if the agent connects but
never speaks, the configured model id is probably not enabled on your LiveKit
project; swap it here or in infra/.env.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime

import structlog

import datamsg
from backend_client import BackendClient
from config import config

log = structlog.get_logger(__name__)

ROOM_PREFIX = "kndl-"
TOPIC = datamsg.TOPIC

# LiveKit-inference model ids (provider/model). Defaults mirror the working
# backend/scripts/livekit_test.py spike for STT/TTS; LLM defaults to a capable
# Google model. Override via env if your LiveKit project enables different ones.
STT_MODEL = os.environ.get("KANDIDLY_INFERENCE_STT", "assemblyai/universal-streaming")
LLM_MODEL = os.environ.get("KANDIDLY_INFERENCE_LLM", "google/gemini-2.5-flash")
TTS_MODEL = os.environ.get("KANDIDLY_INFERENCE_TTS", "cartesia/sonic-2")
TTS_VOICE = os.environ.get("KANDIDLY_INFERENCE_TTS_VOICE", "")
LANGUAGE = os.environ.get("KANDIDLY_LANGUAGE", "en")


def _interview_id_from_room(room_name: str) -> str:
    return (
        room_name[len(ROOM_PREFIX) :]
        if room_name.startswith(ROOM_PREFIX)
        else room_name
    )


def _export_livekit_env() -> None:
    """livekit-agents + inference read LIVEKIT_URL/API_KEY/API_SECRET; we carry
    them as KANDIDLY_LIVEKIT_* so mirror them into the SDK's expected names."""
    if config.livekit_url:
        os.environ.setdefault("LIVEKIT_URL", config.livekit_url)
    if config.livekit_api_key:
        os.environ.setdefault("LIVEKIT_API_KEY", config.livekit_api_key)
    if config.livekit_api_secret:
        os.environ.setdefault("LIVEKIT_API_SECRET", config.livekit_api_secret)


def _background_section(ctx: dict) -> str:
    """Format the cached interview context (resume + scraped sources + requisition
    + key answers) into a compact briefing the interviewer uses for sharp,
    candidate-specific follow-ups. Returns "" when there's nothing useful."""
    if not ctx:
        return ""
    lines: list[str] = []

    req = ctx.get("requisition") or {}
    if req.get("title"):
        role = req["title"] + (f" · {req['domain']}" if req.get("domain") else "")
        lines.append(f"Role: {role}.")
    if req.get("role_objective"):
        lines.append(f"Role objective: {req['role_objective']}")

    name = ctx.get("candidate_display_name")
    if name:
        lines.append(f"Candidate: {name}.")

    for s in ctx.get("sources") or []:
        if s.get("status") != "done":
            continue
        gh, dig = s.get("github") or {}, s.get("digest") or {}
        if gh:
            repos = ", ".join(
                r["name"] for r in (gh.get("top_repos") or [])[:4] if r.get("name")
            )
            bio = f" Bio: {gh['bio']}." if gh.get("bio") else ""
            lines.append(
                f"GitHub (@{gh.get('login')}):{bio}"
                + (f" Repos: {repos}." if repos else "")
            )
        elif dig:
            tech = ", ".join(dig.get("technologies") or [])
            lines.append(
                f"{s.get('kind', 'source').capitalize()} ({s.get('url')}): {dig.get('summary', '')}"
                + (f" Tech: {tech}." if tech else "")
            )
        elif s.get("text"):
            lines.append(
                f"{s.get('kind', 'source').capitalize()} ({s.get('url')}): {s['text'][:300]}"
            )

    key_answers = [
        f"{k}: {(v or {}).get('value')}"
        for k, v in (ctx.get("form") or {}).items()
        if (v or {}).get("role") in ("seed_topic", "context") and (v or {}).get("value")
    ]
    if key_answers:
        lines.append("Application highlights: " + " | ".join(key_answers[:4]) + ".")

    resume_md = (ctx.get("resume") or "").strip()
    if not lines and not resume_md:
        return ""
    body = "\n".join(f"- {ln}" for ln in lines)
    out = (
        "\n# Candidate background (use to personalize and ask sharp, specific "
        f"follow-ups; never read this aloud verbatim)\n{body}\n"
    )
    if resume_md:
        out += f"\n## Candidate resume (Markdown)\n{resume_md}\n"
    return out


# Share of the clock reserved for the greeting and the wrap-up, i.e. not
# available to topic questioning when computing advisory per-topic budgets.
GREET_WRAP_RESERVE = 0.15

_DEFAULT_QUESTIONS = [
    "Tell me about your background and a recent project you're proud of.",
    "Walk me through a technical challenge you solved recently and how you approached it.",
    "How do you debug a tricky production issue under time pressure?",
]


def _topic_budgets(nodes: list[dict], max_seconds: int) -> list[tuple[str, int]]:
    """Pair each planned topic question with an advisory minute budget.

    The plan's per-node soft budgets are drawn against the requisition default,
    so scale them proportionally to THIS interview's clock (minus the
    greeting/wrap reserve). Even split when any budget is missing."""
    topics = [
        (n["seed_question"], n.get("soft_budget_seconds"))
        for n in nodes
        if n.get("seed_question")
        and n.get("node_type") not in ("wrap", "candidate_questions")
    ]
    if not topics:
        topics = [(q, None) for q in _DEFAULT_QUESTIONS]
    available = max(60, int(max_seconds * (1 - GREET_WRAP_RESERVE)))
    budgets = [b for _, b in topics]
    if all(budgets):
        total = sum(budgets)
        scaled = [b * available / total for b in budgets]
    else:
        scaled = [available / len(topics)] * len(topics)
    return [(q, max(1, round(s / 60))) for (q, _), s in zip(topics, scaled)]


def _build_instructions(boot: dict, max_seconds: int) -> str:
    """Assemble the interviewer system prompt from the bootstrapped plan."""
    nodes = boot.get("nodes") or []
    cfg = boot.get("config") or {}
    tone = cfg.get("tone") or "conversational"
    total_min = max(1, round(max_seconds / 60))
    q_lines = "\n".join(
        f"{i + 1}. (about {m} min) {q}"
        for i, (q, m) in enumerate(_topic_budgets(nodes, max_seconds))
    )
    background = _background_section(boot.get("context") or {})
    return f"""You are Kandidly, a warm, professional AI voice interviewer running a spoken screening interview of about {total_min} minutes.

# Speaking style (text-to-speech)
- You are speaking aloud. Reply in plain conversational text only — never markdown, lists, code, or emojis.
- Keep each turn to one to three sentences. Ask ONE question at a time, then stop and let the candidate answer.
- Be encouraging and natural: briefly acknowledge each answer before moving on.
- Maintain a {tone} tone.

# Interview plan — cover these topics in order (minute figures are advisory budgets, not hard stops)
{q_lines}
{background}
# Time management
- A bracketed [Time check …] note appears before your turns with elapsed and remaining time. It is internal — never read it aloud or mention the timer — but always let it drive your pacing.
- Use the whole interview: do not end early while planned topics remain or meaningful time is left, and do not run past the clock.
- Budget so EVERY topic above is asked before the interview ends: the candidate is scored on each topic, and a topic never asked scores zero.
- On or ahead of schedule, go deeper instead of finishing early: ask probing follow-ups on what the candidate just said (their exact role, specifics, trade-offs, what went wrong), and pull in concrete pointers from their resume and application answers above. Prefer depth on the current topic over inventing new topics.
- Behind schedule, stop probing and move on: ask one brief question per remaining topic. Make those questions slightly specific and narrowly scoped — anchor them in a technology or situation from the candidate's background — rather than broad open-ended ones, so even a short answer gives scoreable signal.
- Never pad the interview with filler or small talk.

# Flow
- Open by greeting the candidate, introducing yourself as Kandidly in one sentence, and saying this is a voice screening of about {total_min} minutes. Then ask the first question.
- Work through the topics in order with natural transitions. Do not dump all questions at once.
- When the time check says you are in the wrap-up window, finish quickly: one quick, specific question per topic not yet asked, then close.
- To close, thank the candidate warmly, tell them the hiring team will be in touch, and then stop talking.
"""


def _fmt_span(seconds: int) -> str:
    return f"{seconds} sec" if seconds < 120 else f"{seconds // 60} min"


def _time_note(elapsed: int, remaining: int, wrap_trigger: int) -> str:
    """One-line internal pacing note injected before each interviewer reply —
    the LLM has no clock, so time-awareness must ride the context (SPEC §8.7)."""
    if remaining <= 60:
        directive = (
            "Time is up: give one warm closing sentence now — thank the candidate, "
            "say the hiring team will be in touch, and stop."
        )
    elif remaining <= wrap_trigger:
        directive = (
            "Wrap-up window: ask at most one quick, specific question per topic "
            "not yet covered, then close warmly."
        )
    else:
        directive = (
            "Pace so every remaining topic gets asked; if ahead of schedule, probe "
            "deeper with specific follow-ups instead of ending early."
        )
    return (
        f"[Time check — internal, never read aloud: {_fmt_span(elapsed)} elapsed, "
        f"{_fmt_span(remaining)} remaining. {directive}]"
    )


class InterviewRunner:
    """Holds per-interview state and wires the AgentSession to the backend."""

    def __init__(
        self, ctx, backend: BackendClient, interview_id: str, max_seconds: int
    ):
        self.ctx = ctx
        self.room = ctx.room
        self.backend = backend
        self.interview_id = interview_id
        self.max_seconds = max_seconds
        self.wrap_trigger = config.wrap_trigger_seconds
        self._seq = 0
        self._candidate_turns = 0
        self._turns: asyncio.Queue = asyncio.Queue()
        self._start = time.monotonic()
        self._ended = asyncio.Event()

    # --- data channel helpers ---
    async def _publish(self, payload: bytes) -> None:
        try:
            await self.room.local_participant.publish_data(
                payload, topic=TOPIC, reliable=True
            )
        except Exception as exc:  # noqa: BLE001 - best-effort UI mirror
            log.warning("publish_data_failed", error=str(exc))

    def on_conversation_item(self, ev) -> None:
        """Sync handler for `conversation_item_added` — enqueue for ordered write.

        For the assistant, this event only fires once the turn's TTS audio has
        *finished* forwarding (agent_activity.py plays out the full generation
        before emitting it), so stamping started_at with "now" here lands near
        the END of the turn — the review page then always shows the highlight
        one turn behind the voice. Use the SDK's own start-of-speech timestamp
        instead: `metrics.started_speaking_at` (first audio frame) for the
        agent, falling back to `created_at` (set at message construction, i.e.
        near the true start) for both roles.
        """
        item = getattr(ev, "item", None)
        role = getattr(item, "role", None)
        text = (getattr(item, "text_content", None) or "").strip()
        if role not in ("user", "assistant") or not text:
            return
        speaker = "candidate" if role == "user" else "kandidly"
        if speaker == "candidate":
            self._candidate_turns += 1
        self._seq += 1
        started_at_epoch = (
            item.metrics.get("started_speaking_at") if item.metrics else None
        ) or item.created_at
        started_at = datetime.fromtimestamp(started_at_epoch, tz=UTC)
        self._turns.put_nowait((self._seq, speaker, text, started_at))

    async def drain_turns(self) -> None:
        """Single consumer → guarantees monotonic seq to the backend."""
        while True:
            seq, speaker, text, started_at = await self._turns.get()
            try:
                await self.backend.create_turn(
                    self.interview_id,
                    seq=seq,
                    speaker=speaker,
                    text=text,
                    started_at=started_at,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("create_turn_failed", seq=seq, error=str(exc))
            await self._publish(datamsg.caption_final(speaker, text, seq))

    def time_note(self) -> str:
        elapsed = int(time.monotonic() - self._start)
        remaining = max(0, self.max_seconds - elapsed)
        return _time_note(elapsed, remaining, self.wrap_trigger)

    async def run_timer(self) -> None:
        while not self._ended.is_set():
            elapsed = int(time.monotonic() - self._start)
            remaining = max(0, self.max_seconds - elapsed)
            phase = "wrap" if remaining <= self.wrap_trigger else "live"
            await self._publish(datamsg.control_timer(elapsed, remaining, phase))
            if remaining <= 0:
                log.info("interview_time_cap", interview_id=self.interview_id)
                await self.end("time_cap")
                return
            try:
                await asyncio.wait_for(self._ended.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    async def end(self, reason: str) -> None:
        if self._ended.is_set():
            return
        self._ended.set()
        elapsed = int(time.monotonic() - self._start)
        await self._publish(datamsg.control_state("ended"))
        try:
            await self.backend.set_status(
                self.interview_id,
                "ended",
                end_reason=reason,
                elapsed_active_seconds=elapsed,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("set_status_ended_failed", error=str(exc))
        log.info(
            "interview_ended",
            interview_id=self.interview_id,
            reason=reason,
            elapsed=elapsed,
        )


async def entrypoint(ctx) -> None:
    """Accept a `kndl-*` room, conduct the interview, persist everything."""
    from livekit.agents import Agent, AgentSession, inference

    await ctx.connect()
    room = ctx.room
    if not room.name.startswith(ROOM_PREFIX):
        log.info("ignoring_non_interview_room", room=room.name)
        return

    interview_id = _interview_id_from_room(room.name)
    log.info("agent_job_accepted", room=room.name, interview_id=interview_id)

    backend = BackendClient()
    try:
        try:
            boot = await backend.bootstrap(interview_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("bootstrap_failed", interview_id=interview_id, error=str(exc))
            boot = {}

        cfg = boot.get("config") or {}
        max_seconds = int(
            cfg.get("max_duration_seconds") or config.max_interview_seconds
        )
        instructions = _build_instructions(boot, max_seconds)

        # AgentSession bundles a default silero VAD (livekit-agents 1.6), so no
        # explicit vad= is needed.
        session = AgentSession(
            stt=inference.STT(model=STT_MODEL, language=LANGUAGE),
            llm=inference.LLM(model=LLM_MODEL),
            tts=inference.TTS(
                model=TTS_MODEL,
                language=LANGUAGE,
                **({"voice": TTS_VOICE} if TTS_VOICE else {}),
            ),
        )

        runner = InterviewRunner(ctx, backend, interview_id, max_seconds)
        session.on("conversation_item_added", runner.on_conversation_item)

        class TimeAwareAgent(Agent):
            """Injects the live clock into each LLM call — the model can't sense
            elapsed time, so pacing (fill vs. wrap) must ride the turn context."""

            async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
                turn_ctx.add_message(role="system", content=runner.time_note())

        # Mark the interview live before the first utterance (SPEC §8.3).
        try:
            await backend.set_status(interview_id, "live")
        except Exception as exc:  # noqa: BLE001
            log.warning("set_status_live_failed", error=str(exc))
        await runner._publish(datamsg.control_state("live"))

        drain_task = asyncio.create_task(runner.drain_turns())
        timer_task = asyncio.create_task(runner.run_timer())

        async def _on_shutdown(*_a, **_k) -> None:
            # Candidate left / job ending — finalize if not already ended.
            reason = "completed" if runner._candidate_turns > 0 else "abandoned"
            await runner.end(reason)
            drain_task.cancel()
            timer_task.cancel()
            await backend.aclose()

        ctx.add_shutdown_callback(_on_shutdown)

        await session.start(agent=TimeAwareAgent(instructions=instructions), room=room)
        # Kick off the interview: greet + first question.
        await session.generate_reply(
            instructions="Greet the candidate, introduce yourself as Kandidly in one sentence, "
            f"say this is a voice screening of about {max(1, round(max_seconds / 60))} minutes, "
            "then ask the first question from the plan."
        )
    except Exception:
        await backend.aclose()
        raise


def main() -> None:
    from livekit.agents import WorkerOptions, cli

    _export_livekit_env()
    log.info(
        "agent_worker_boot",
        livekit_url=config.livekit_url or "(unset)",
        agent_name=config.livekit_agent_name,
        stt=STT_MODEL,
        llm=LLM_MODEL,
        tts=TTS_MODEL,
    )
    # ws_url/api_key/api_secret are read from the LIVEKIT_* env exported above.
    # agent_name switches this worker to explicit dispatch: it only gets jobs
    # for rooms whose candidate token names it (config.py explains why).
    cli.run_app(
        WorkerOptions(entrypoint_fnc=entrypoint, agent_name=config.livekit_agent_name)
    )


if __name__ == "__main__":
    main()
