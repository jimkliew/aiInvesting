"""Coder Agent: one hypothesis in, one generate_signals() out. Repairs on feedback."""
from __future__ import annotations

import re

from .. import prompts
from ..schemas import Hypothesis, StrategyCode

FENCE = re.compile(r"^```(?:python)?\s*\n|\n```\s*$", re.MULTILINE)


def strip_fences(code: str) -> str:
    return FENCE.sub("", code.strip()).strip() + "\n"


def write_code(llm, hyp: Hypothesis, catalog: str, feedback: str | None = None,
               lessons: list[str] | None = None, agent: str = "coder") -> StrategyCode:
    system = prompts.load("coder", lessons=lessons)
    user = (f"Hypothesis: {hyp.name} [{hyp.family}]\n{hyp.idea}\n"
            f"Features it expects to use: {', '.join(hyp.features_used) or 'any'}\n\n"
            f"{catalog}\n")
    if feedback:
        user += f"\nYour previous attempt failed with this error:\n{feedback}\nReturn the full corrected function."
    out: StrategyCode = llm.structured(system, user, StrategyCode, agent=agent)
    out.code = strip_fences(out.code)
    return out
