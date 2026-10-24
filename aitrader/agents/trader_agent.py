"""Trader personas: one weekly decision per ticker from a point-in-time snapshot."""
from __future__ import annotations

from .. import prompts
from ..schemas import Decision

PERSONAS = ["momentum", "contrarian", "risk_averse"]


def decide(llm, persona: str, snapshot_text: str, lessons: list[str] | None, max_weight: float,
           current_weight: float, agent: str | None = None) -> Decision:
    name = f"trader_{persona}"
    system = prompts.load(name, lessons=lessons)
    user = f"{snapshot_text}\n\nmax_weight: {max_weight:.2f}\nDecide for this ticker."
    d: Decision = llm.structured(system, user, Decision, agent=agent or name)
    tw = d.target_weight
    if tw != tw:  # NaN guard
        tw = current_weight
    if tw > 1.0:  # the model answered in percent
        tw = tw / 100.0
    d.target_weight = round(min(max(tw, 0.0), max_weight), 4)
    d.confidence = round(min(max(d.confidence, 0.0), 1.0), 3)
    if d.action == "HOLD":
        d.target_weight = round(min(current_weight, max_weight), 4)
    elif d.target_weight > current_weight + 1e-9:
        d.action = "BUY"
    elif d.target_weight < current_weight - 1e-9:
        d.action = "SELL"
    else:
        d.action = "HOLD"
    return d
