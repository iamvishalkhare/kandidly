"""Evidence packet assembly for per-criterion scoring (SPEC §11.2).

Pure logic — takes plain dicts/lists, no DB, no LLM. The DB loading shim that
converts ORM rows to the plain-dict form lives in app/jobs/interviews.py so
this module is fully unit-testable without a database or provider keys.
"""

from __future__ import annotations

from dataclasses import dataclass

# ~6 000 tokens at ~4 chars/token; we drop from the START to keep the latest
# context (SPEC §11.2 "keep latest").
_MAX_SLICE_CHARS: int = 24_000


@dataclass
class EvidencePacket:
    criterion: dict  # {key, name, description, level_anchors, weight}
    transcript_slice: list[dict]  # [{turn_id, speaker, text}] ordered by seq
    notes: list[dict]  # [{turn_id, signal, note}] for this criterion
    coverage_note: str  # "" or "no targeted turns"


def build_evidence_packet(
    criterion: dict,
    all_turns: list[dict],
    node_target_criteria: dict[str, list[str]],
    evidence_notes: list[dict],
) -> EvidencePacket:
    """Build an evidence packet for one rubric criterion.

    Parameters
    ----------
    criterion:
        Dict with keys: key, name, description, level_anchors, weight.
    all_turns:
        All turns for the interview as plain dicts with keys:
        id, seq, speaker, text, node_id (str or None).
    node_target_criteria:
        Mapping from node_id (str) to the list of criterion keys it targets.
    evidence_notes:
        All evidence_notes for the interview as plain dicts with keys:
        id, turn_id, criterion_key, signal, note.

    Algorithm (SPEC §11.2)
    ----------------------
    (a) turns whose node's target_criteria contains criterion.key
    (b) turns referenced by evidence_notes for criterion.key
    (c) ±1 adjacent turn (by seq) for context around each turn in (a)∪(b)
    Dedupe, order by seq.  Coverage gap when (a) is empty.
    Cap slice at _MAX_SLICE_CHARS — drop from the START, keep the latest turns.
    """
    ckey: str = criterion["key"]

    # Index turns by id and by seq for O(1) adjacency look-ups.
    turn_by_seq: dict[int, dict] = {t["seq"]: t for t in all_turns}

    # (a) targeted turns: node covers this criterion key.
    targeted_ids: set[str] = set()
    for turn in all_turns:
        node_id = turn.get("node_id")
        if node_id and ckey in node_target_criteria.get(node_id, []):
            targeted_ids.add(turn["id"])

    coverage_gap: bool = len(targeted_ids) == 0
    coverage_note: str = "no targeted turns" if coverage_gap else ""

    # (b) turns referenced by evidence_notes for this criterion.
    relevant_notes = [n for n in evidence_notes if n.get("criterion_key") == ckey]
    note_turn_ids: set[str] = {n["turn_id"] for n in relevant_notes}

    # (c) ±1 adjacent turns.
    seed_ids: set[str] = targeted_ids | note_turn_ids
    adjacent_ids: set[str] = set()
    for turn in all_turns:
        if turn["id"] in seed_ids:
            seq = turn["seq"]
            for adj_seq in (seq - 1, seq + 1):
                adj = turn_by_seq.get(adj_seq)
                if adj:
                    adjacent_ids.add(adj["id"])

    # Union, dedupe, sort by seq.
    included_ids: set[str] = seed_ids | adjacent_ids
    sorted_turns = sorted(
        (t for t in all_turns if t["id"] in included_ids),
        key=lambda t: t["seq"],
    )

    # Build slice entries.
    slice_entries: list[dict] = [
        {"turn_id": t["id"], "speaker": t["speaker"], "text": t["text"]} for t in sorted_turns
    ]

    # Cap to _MAX_SLICE_CHARS — drop from the start, keep the latest.
    total_chars = sum(len(e["text"]) for e in slice_entries)
    while total_chars > _MAX_SLICE_CHARS and slice_entries:
        removed = slice_entries.pop(0)
        total_chars -= len(removed["text"])

    return EvidencePacket(
        criterion=criterion,
        transcript_slice=slice_entries,
        notes=[
            {"turn_id": n["turn_id"], "signal": n["signal"], "note": n["note"]}
            for n in relevant_notes
        ],
        coverage_note=coverage_note,
    )
