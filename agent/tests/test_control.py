"""parse_ctrl + apply_overrides (SPEC §8.7, §18.1). Covers valid, malformed JSON,
missing prefix, ctrl-only output, unicode, oversized f, and prefix appearing
mid-stream (must not trigger)."""

from __future__ import annotations

from control import (
    MAX_FOCUS,
    Ctrl,
    OverrideContext,
    apply_overrides,
    default_ctrl,
    parse_ctrl,
    split_output,
)


def test_valid_line():
    c = parse_ctrl('@@CTRL {"d":"ASK","n":"node1","f":"","end":false}')
    assert c == Ctrl(d="ASK", n="node1", f="", end=False)


def test_malformed_json_returns_none():
    assert parse_ctrl('@@CTRL {"d":"ASK", oops}') is None


def test_missing_prefix_returns_none():
    assert parse_ctrl('{"d":"ASK","n":"n"}') is None


def test_unknown_decision_returns_none():
    assert parse_ctrl('@@CTRL {"d":"THINK","n":"n","f":"","end":false}') is None


def test_unicode_focus_ok():
    c = parse_ctrl('@@CTRL {"d":"PROBE","n":"n","f":"café ☕ 深挖","end":true}')
    assert c is not None and c.end is True and "café" in c.f


def test_oversized_focus_truncated():
    big = "x" * (MAX_FOCUS + 500)
    c = parse_ctrl('@@CTRL {"d":"PROBE","n":"n","f":"' + big + '","end":false}')
    assert c is not None and len(c.f) == MAX_FOCUS


def test_prefix_mid_stream_not_triggered():
    text = "Sure, let me explain.\n@@CTRL {\"d\":\"ASK\",\"n\":\"n\"}"
    first, _ = split_output(text)
    assert parse_ctrl(first) is None


def test_ctrl_only_output_has_empty_utterance():
    text = '@@CTRL {"d":"CLOSE","n":"wrap","f":"","end":true}'
    first, spoken = split_output(text)
    assert parse_ctrl(first) is not None
    assert spoken == ""


def test_split_output_strips_ctrl_line():
    text = '@@CTRL {"d":"ASK","n":"n","f":"","end":false}\nHello there, tell me about yourself.'
    first, spoken = split_output(text)
    assert first.startswith("@@CTRL")
    assert spoken == "Hello there, tell me about yourself."


def test_default_ctrl_is_probe():
    assert default_ctrl("nX") == Ctrl(d="PROBE", n="nX", f="", end=False)


# --- overrides --------------------------------------------------------------
def _ctx(**kw):
    base = dict(current_node_id="n1", followups_used=0, max_followups=2,
                wrap_phase=False, injection_node_id=None, remaining_node_ids=("n2",))
    base.update(kw)
    return OverrideContext(**base)


def test_followup_cap_downgrades_probe():
    res = apply_overrides(Ctrl("PROBE", "n1", "depth", False), _ctx(followups_used=2))
    assert res.ctrl.d == "ADVANCE"
    assert "followup_cap" in res.overrides_applied


def test_wrap_phase_forces_wrap():
    res = apply_overrides(Ctrl("ASK", "n1", "", False), _ctx(wrap_phase=True))
    assert res.ctrl.d == "WRAP"


def test_wrap_phase_does_not_override_close():
    res = apply_overrides(Ctrl("CLOSE", "wrap", "", True), _ctx(wrap_phase=True))
    assert res.ctrl.d == "CLOSE"


def test_injection_forces_advance():
    res = apply_overrides(Ctrl("PROBE", "n1", "", False), _ctx(injection_node_id="inj9"))
    assert res.ctrl.d == "ADVANCE"
    assert res.ctrl.n == "inj9"


def test_no_remaining_nodes_advance_becomes_wrap():
    res = apply_overrides(Ctrl("ADVANCE", "n2", "", True), _ctx(remaining_node_ids=()))
    assert res.ctrl.d == "WRAP"
