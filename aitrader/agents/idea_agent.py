"""Idea Agent: reads the notebook, proposes distinct hypotheses. No tools."""
from __future__ import annotations

import re

from .. import prompts
from ..schemas import Hypotheses, Hypothesis


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s[:48] or "strategy"


def describe_focus(family_focus: dict | None) -> str:
    if not family_focus:
        return "no preference"
    emph = family_focus.get("emphasise") or []
    avoid = family_focus.get("avoid") or []
    parts = []
    if emph:
        parts.append("emphasise " + ", ".join(emph))
    if avoid:
        parts.append("avoid " + ", ".join(avoid))
    return "; ".join(parts) or "no preference"


def propose(llm, k: int, catalog: str, notebook_summary: str, family_focus: dict | None,
            lessons: list[str] | None, existing_names: set[str] | None = None, agent: str = "idea") -> list[Hypothesis]:
    system = prompts.load("idea", lessons=lessons, k=k, focus=describe_focus(family_focus))
    user = (f"Features available:\n{catalog}\n\n"
            f"Lab notebook, what was tried before and how it scored:\n{notebook_summary}\n\n"
            f"Propose {k} new hypotheses.")
    out: Hypotheses = llm.structured(system, user, Hypotheses, agent=agent)
    seen = set(existing_names or ())
    items: list[Hypothesis] = []
    for h in out.items:
        name = slug(h.name)
        if name in seen:
            name = f"{name}_v{len([s for s in seen if s.startswith(name)]) + 1}"
        seen.add(name)
        h.name = name
        items.append(h)
        if len(items) >= k:
            break
    return items
