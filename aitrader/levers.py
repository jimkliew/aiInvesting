"""The lever menu (practice P17): the only way the Review Agent can change the team.

Everything the coach asks for goes through apply(). Out-of-menu or out-of-range
requests raise InvalidLever and are logged, never applied.
"""
from __future__ import annotations

import re

from .config import RANGES
from .schemas import Recommendation
from .store import RunStore

AGENTS = {"idea", "coder", "critic", "trader_momentum", "trader_contrarian", "trader_risk_averse", "data"}
FAMILIES = {"trend", "mean_reversion", "volatility", "cross_sectional"}
MAX_LESSON_CHARS = 300


class InvalidLever(Exception):
    pass


def _agent(name: str) -> str:
    a = name.strip().lower().replace(" ", "_").replace("-", "_")
    a = a.removesuffix("_agent").removeprefix("the_")
    aliases = {"trader": "trader_momentum", "momentum": "trader_momentum", "contrarian": "trader_contrarian",
               "risk_averse": "trader_risk_averse", "reviewer": "critic"}
    a = aliases.get(a, a)
    if a not in AGENTS:
        raise InvalidLever(f"unknown agent {name!r}; allowed: {sorted(AGENTS)}")
    return a


def _int(s: str) -> int:
    m = re.search(r"\d+", str(s))
    if not m:
        raise InvalidLever(f"expected a number, got {s!r}")
    return int(m.group())


def parse_focus(text: str) -> dict:
    t = text.lower().replace("mean reversion", "mean_reversion").replace("cross sectional", "cross_sectional")
    emph, avoid = [], []
    for part in re.split(r"[;\n]", t):
        words = re.findall(r"[a-z_]+", part)
        if not words:
            continue
        fams = [w for w in words if w in FAMILIES]
        if "avoid" in words or "de_emphasise" in words or "deemphasise" in words:
            avoid += fams
        else:
            emph += fams
    if not emph and not avoid:
        raise InvalidLever(f"no families recognised in {text!r}; allowed: {sorted(FAMILIES)}")
    return {"emphasise": sorted(set(emph)), "avoid": sorted(set(avoid) - set(emph))}


def apply(store: RunStore, rec: Recommendation, season: int, source: str = "coach") -> dict:
    lever = rec.lever
    before = after = None
    detail: dict = {}
    if lever == "add_lesson":
        agent = _agent(rec.target)
        text = rec.change.strip()
        if not text:
            raise InvalidLever("add_lesson needs the lesson text in `change`")
        if len(text) > MAX_LESSON_CHARS:
            raise InvalidLever(f"lesson is {len(text)} chars; limit {MAX_LESSON_CHARS}")
        lid = store.add_lesson(agent, text, season=season)
        detail = {"lesson_id": lid}
        target, change = agent, text
    elif lever == "remove_lesson":
        agent = _agent(rec.target)
        lid = _int(rec.change)
        existing = {l["id"]: l for l in store.lessons(agent)}
        if lid not in existing:
            raise InvalidLever(f"{agent} has no lesson {lid}")
        before = existing[lid]["text"]
        store.remove_lesson(agent, lid)
        detail = {"lesson_id": lid, "removed_text": before}
        target, change = agent, str(lid)
    elif lever == "set_param":
        name = rec.target.strip()
        if name not in RANGES:
            raise InvalidLever(f"{name!r} is not adjustable; allowed: {sorted(RANGES)}")
        before = store.params.get(name)
        raw = rec.change.strip().strip('"').strip("'")
        if isinstance(RANGES[name], set):
            value = raw.lower()
        else:
            m = re.search(r"-?\d+(\.\d+)?", raw)
            if not m:
                raise InvalidLever(f"set_param {name} needs a numeric value, got {raw!r}")
            value = float(m.group())
            if name == "desk.max_weight" and value > 1:
                value = value / 100.0
        try:
            after = store.params.validate_set(name, value)
        except ValueError as e:
            raise InvalidLever(str(e))
        store.save_params()
        target, change = name, str(after)
    elif lever == "set_family_focus":
        before = dict(store.params.get("family_focus") or {})
        after = parse_focus(rec.change)
        store.params["family_focus"] = after
        store.save_params()
        target, change = "idea", f"emphasise {', '.join(after['emphasise']) or 'none'}; avoid {', '.join(after['avoid']) or 'none'}"
    elif lever in ("retire_strategy", "reinstate_strategy"):
        name = rec.target.strip()
        names = {e["name"] for e in store.notebook()}
        if name not in names:
            raise InvalidLever(f"no strategy named {name!r} in the notebook")
        (store.retire if lever == "retire_strategy" else store.reinstate)(name)
        target, change = name, ""
    elif lever == "revert":
        return revert(store, _int(rec.target), season, rationale=rec.rationale, source=source)
    else:
        raise InvalidLever(f"unknown lever {lever!r}")
    return store.changelog_append({
        "season": season, "lever": lever, "target": target, "change": change, "rationale": rec.rationale,
        "expected_effect": rec.expected_effect, "revert_if": rec.revert_if, "before": before, "after": after,
        "detail": detail, "source": source,
    })


def revert(store: RunStore, change_id: int, season: int, rationale: str = "", source: str = "coach") -> dict:
    rows = {c["id"]: c for c in store.changelog()}
    c = rows.get(change_id)
    if c is None:
        raise InvalidLever(f"no change {change_id}")
    if c.get("status") != "active" or c["lever"] == "revert":
        raise InvalidLever(f"change {change_id} cannot be reverted (status {c.get('status')})")
    lever = c["lever"]
    if lever == "add_lesson":
        store.remove_lesson(c["target"], c["detail"]["lesson_id"])
    elif lever == "remove_lesson":
        store.add_lesson(c["target"], c["detail"]["removed_text"], season=season)
    elif lever == "set_param":
        store.params.validate_set(c["target"], c["before"])
        store.save_params()
    elif lever == "set_family_focus":
        store.params["family_focus"] = c["before"] or {"emphasise": [], "avoid": []}
        store.save_params()
    elif lever == "retire_strategy":
        store.reinstate(c["target"])
    elif lever == "reinstate_strategy":
        store.retire(c["target"])
    new = store.changelog_append({"season": season, "lever": "revert", "target": str(change_id), "change": f"undo {lever} {c['target']}",
                                  "rationale": rationale, "before": c.get("after"), "after": c.get("before"), "source": source})
    store.update_change(change_id, status="reverted", reverted_by=new["id"])
    return new
