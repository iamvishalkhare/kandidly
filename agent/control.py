"""Control-prefix protocol parser + enforcement overrides (SPEC §8.7). Pure and
heavily unit-tested — no I/O, no LiveKit, no network.

The interviewer LLM MUST begin every turn with exactly one control line:
    @@CTRL {"d":"ASK","n":"<node_id>","f":"","end":false}
then a newline, then only the words to speak.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

CTRL_PREFIX = "@@CTRL "
MAX_FOCUS = 200

DECISIONS: frozenset[str] = frozenset(
    {"GREET", "ASK", "PROBE", "CLARIFY", "ADVANCE", "WRAP", "CLOSE"}
)


@dataclass(frozen=True)
class Ctrl:
    d: str  # decision
    n: str  # node_id the decision applies to
    f: str  # short focus (probe target); may be empty
    end: bool  # current node complete


def parse_ctrl(first_line: str) -> Ctrl | None:
    """Parse the control line. Returns None if missing/malformed — the caller
    then substitutes the safe default (SPEC §8.7) and logs a ctrl_parse_error.

    Only the FIRST line is considered: a `@@CTRL` token appearing later in the
    stream MUST NOT be treated as control.
    """
    if not first_line.startswith(CTRL_PREFIX):
        return None
    payload = first_line[len(CTRL_PREFIX):].strip()
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None

    d = obj.get("d")
    if d not in DECISIONS:
        return None

    n = obj.get("n", "")
    f = obj.get("f", "")
    end = obj.get("end", False)
    if not isinstance(n, str) or not isinstance(f, str) or not isinstance(end, bool):
        return None
    if len(f) > MAX_FOCUS:
        f = f[:MAX_FOCUS]
    return Ctrl(d=d, n=n, f=f, end=end)


def split_output(text: str) -> tuple[str, str]:
    """Split raw LLM output into (first_line, remainder-to-speak). The control
    line is stripped so `@@CTRL ...` is never spoken."""
    newline = text.find("\n")
    if newline == -1:
        return text, ""  # ctrl-only output → nothing to speak
    return text[:newline], text[newline + 1:].lstrip("\n")


def default_ctrl(current_node_id: str) -> Ctrl:
    """Safe fallback when the control line is missing/malformed (SPEC §8.7)."""
    return Ctrl(d="PROBE", n=current_node_id, f="", end=False)


# --------------------------------------------------------------------------- #
# Enforcement overrides (SPEC §8.7) — applied agent-side regardless of model.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OverrideContext:
    current_node_id: str
    followups_used: int
    max_followups: int
    wrap_phase: bool  # timekeeper says wrap (status wrap_up)
    injection_node_id: str | None  # a queued injected node to force ADVANCE into
    remaining_node_ids: tuple[str, ...]  # non-terminal nodes still pending/active


@dataclass(frozen=True)
class OverrideResult:
    ctrl: Ctrl
    overrides_applied: tuple[str, ...]


def apply_overrides(ctrl: Ctrl, ctx: OverrideContext) -> OverrideResult:
    """Deterministic override table (SPEC §8.7). Order matters:
    injection > followup-cap > wrap > empty-nodes."""
    applied: list[str] = []
    out = ctrl

    # Injection queued ⇒ force ADVANCE to the injected node.
    if ctx.injection_node_id is not None and out.d != "CLOSE":
        out = replace(out, d="ADVANCE", n=ctx.injection_node_id, end=True)
        applied.append("injection_forced_advance")

    # followups_used ≥ max_followups ⇒ downgrade PROBE → ADVANCE.
    if out.d == "PROBE" and ctx.followups_used >= ctx.max_followups:
        out = replace(out, d="ADVANCE", end=True)
        applied.append("followup_cap")

    # Wrap phase ⇒ any decision except CLOSE becomes WRAP.
    if ctx.wrap_phase and out.d != "CLOSE":
        out = replace(out, d="WRAP")
        applied.append("wrap_phase")

    # Remaining nodes empty ⇒ ADVANCE becomes WRAP (then CLOSE next turn).
    if out.d == "ADVANCE" and not ctx.remaining_node_ids:
        out = replace(out, d="WRAP")
        applied.append("no_remaining_nodes")

    return OverrideResult(ctrl=out, overrides_applied=tuple(applied))
