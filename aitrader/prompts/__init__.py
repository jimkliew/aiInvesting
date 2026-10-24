"""Prompt files, one per agent. Lessons from the coach are appended as a separate block."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).parent


def load(name: str, lessons: list[str] | None = None, **vars) -> str:
    text = (PROMPT_DIR / f"{name}.md").read_text()
    for k, v in vars.items():
        text = text.replace("{" + k + "}", str(v))
    if lessons:
        text = text.rstrip() + "\n\n## Lessons from the coach\n" + "\n".join(lessons) + "\n"
    return text


def raw(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text()


def save(name: str, text: str) -> None:
    (PROMPT_DIR / f"{name}.md").write_text(text)


def list_agents() -> list[str]:
    return sorted(p.stem for p in PROMPT_DIR.glob("*.md"))
