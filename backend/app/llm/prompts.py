"""Prompt registry (SPEC §8.9). Prompts live as versioned markdown files under
prompts/{name}_{version}.md and are referenced by (name, version). The version
string is persisted on every artifact a prompt produces."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache
def load_prompt(name: str, version: str) -> str:
    """Return the raw prompt text for (name, version), e.g. ('interviewer','v1')."""
    path = _PROMPT_DIR / f"{name}_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path.name}")
    return path.read_text(encoding="utf-8")


# Current version pins (SPEC §8.9 — bump by adding a new file, never editing).
PROMPT_VERSIONS = {
    "extract": "v1",
    "plan": "v1",
    "interviewer": "v1",
    "score": "v1",
    "report": "v1",
    "annotate": "v1",
}


def version_tag(name: str) -> str:
    """The full persisted version tag, e.g. 'plan_v1'."""
    return f"{name}_{PROMPT_VERSIONS[name]}"
