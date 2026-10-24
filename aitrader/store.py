"""Run store: everything a campaign produces, as plain files (practice P10, P15).

runs/<campaign>/
  campaign.json        universe, params at start, model, options
  params.json          current lever-adjustable params
  trace.jsonl          every event (see events.py)
  notebook.jsonl       every strategy tried, one line each
  lessons.json         per-agent lessons added by the coach
  changelog.jsonl      every change the coach (or a human) applied
  track_record.json    one row per scored season
  seasons/<n>/         scorecard.json, book.json, decisions.jsonl, review.json, *.parquet
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Params


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _append_jsonl(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(d, default=str) + "\n")


def _read_json(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def _write_json(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, default=str))


class RunStore:
    def __init__(self, root: str | Path = "runs", campaign_id: str | None = None):
        self.root = Path(root)
        self.id = campaign_id or datetime.now().strftime("campaign-%Y%m%d-%H%M%S")
        self.dir = self.root / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.params: Params = Params(_read_json(self.dir / "params.json", None) or Params.defaults())

    # ---- paths ----
    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def season_dir(self, n: int) -> Path:
        d = self.dir / "seasons" / f"{n:02d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---- campaign meta and params ----
    def save_meta(self, **meta: Any) -> None:
        m = self.meta()
        m.update(meta)
        _write_json(self.dir / "campaign.json", m)

    def meta(self) -> dict:
        return _read_json(self.dir / "campaign.json", {})

    def save_params(self) -> None:
        _write_json(self.dir / "params.json", dict(self.params))

    # ---- notebook ----
    def notebook_add(self, entry: dict) -> dict:
        entry = {"ts": _now(), **entry}
        _append_jsonl(self.dir / "notebook.jsonl", entry)
        return entry

    def notebook(self) -> list[dict]:
        return _read_jsonl(self.dir / "notebook.jsonl")

    def retired(self) -> set[str]:
        return set(_read_json(self.dir / "retired.json", []))

    def retire(self, name: str) -> None:
        _write_json(self.dir / "retired.json", sorted(self.retired() | {name}))

    def reinstate(self, name: str) -> None:
        _write_json(self.dir / "retired.json", sorted(self.retired() - {name}))

    def kept(self) -> list[dict]:
        """Latest kept entry per strategy name, excluding retired ones."""
        latest: dict[str, dict] = {}
        for e in self.notebook():
            if e.get("status") == "kept":
                latest[e["name"]] = e
        ret = self.retired()
        return [e for n, e in latest.items() if n not in ret]

    def notebook_summary(self, max_lines: int = 30) -> str:
        rows = self.notebook()
        if not rows:
            return "(empty: nothing tried yet)"
        ret = self.retired()
        lines = []
        for e in rows[-max_lines:]:
            val = (e.get("val") or {}).get("sharpe")
            tr = (e.get("train") or {}).get("sharpe")
            turn = (e.get("val") or {}).get("turnover")
            tag = "retired" if e["name"] in ret else e.get("status", "?")
            lines.append(
                f"- S{e.get('season', '?')} {e['name']} [{e.get('family', '?')}] {tag}: "
                f"train Sharpe {tr if tr is not None else 'n/a'}, val Sharpe {val if val is not None else 'n/a'}, "
                f"turnover {turn if turn is not None else 'n/a'}%/yr. {e.get('idea', '')[:90]}"
            )
        return "\n".join(lines)

    # ---- lessons ----
    def _lessons_doc(self) -> dict:
        return _read_json(self.dir / "lessons.json", {"next_id": 1, "agents": {}})

    def lessons(self, agent: str) -> list[dict]:
        return list(self._lessons_doc()["agents"].get(agent, []))

    def lesson_texts(self, agent: str) -> list[str]:
        return [f"{l['id']}. (after S{l.get('season', '?')}) {l['text']}" for l in self.lessons(agent)]

    def add_lesson(self, agent: str, text: str, season: int | None = None, change_id: int | None = None) -> int:
        doc = self._lessons_doc()
        lid = doc["next_id"]
        doc["next_id"] = lid + 1
        doc["agents"].setdefault(agent, []).append({"id": lid, "text": text, "season": season, "change_id": change_id})
        _write_json(self.dir / "lessons.json", doc)
        return lid

    def remove_lesson(self, agent: str, lesson_id: int) -> bool:
        doc = self._lessons_doc()
        before = len(doc["agents"].get(agent, []))
        doc["agents"][agent] = [l for l in doc["agents"].get(agent, []) if int(l["id"]) != int(lesson_id)]
        _write_json(self.dir / "lessons.json", doc)
        return len(doc["agents"][agent]) < before

    def all_lessons(self) -> dict[str, list[dict]]:
        return self._lessons_doc()["agents"]

    # ---- changelog ----
    def changelog(self) -> list[dict]:
        return _read_jsonl(self.dir / "changelog.jsonl")

    def changelog_append(self, change: dict) -> dict:
        rows = self.changelog()
        change = {"id": len(rows) + 1, "ts": _now(), "status": "active", **change}
        _append_jsonl(self.dir / "changelog.jsonl", change)
        return change

    def update_change(self, change_id: int, **fields: Any) -> None:
        rows = self.changelog()
        for r in rows:
            if r["id"] == change_id:
                r.update(fields)
        p = self.dir / "changelog.jsonl"
        p.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))

    # ---- quant book ----
    def set_quant_book(self, season: int, name: str, code: str, val_sharpe: float | None, fallback: bool = False) -> None:
        _write_json(self.season_dir(season) / "book.json",
                    {"season": season, "name": name, "code": code, "val_sharpe": val_sharpe, "fallback": fallback})

    def quant_book(self, season: int) -> dict | None:
        return _read_json(self.season_dir(season) / "book.json", None)

    # ---- seasons ----
    def save_scorecard(self, n: int, scorecard: dict) -> None:
        _write_json(self.season_dir(n) / "scorecard.json", scorecard)

    def scorecard(self, n: int) -> dict | None:
        return _read_json(self.season_dir(n) / "scorecard.json", None)

    def save_weights(self, n: int, name: str, weights: pd.DataFrame) -> None:
        weights.to_parquet(self.season_dir(n) / f"{name}.parquet")

    def weights(self, n: int, name: str) -> pd.DataFrame | None:
        p = self.season_dir(n) / f"{name}.parquet"
        return pd.read_parquet(p) if p.exists() else None

    def add_decision(self, n: int, decision: dict) -> None:
        _append_jsonl(self.season_dir(n) / "decisions.jsonl", {"ts": _now(), **decision})

    def decisions(self, n: int | None = None) -> list[dict]:
        if n is not None:
            return _read_jsonl(self.season_dir(n) / "decisions.jsonl")
        out = []
        for d in sorted((self.dir / "seasons").glob("*/decisions.jsonl")) if (self.dir / "seasons").exists() else []:
            out.extend(_read_jsonl(d))
        return out

    def save_review(self, n: int, review: dict) -> None:
        _write_json(self.season_dir(n) / "review.json", {"season": n, **review})

    def reviews(self) -> list[dict]:
        out = []
        for p in sorted((self.dir / "seasons").glob("*/review.json")) if (self.dir / "seasons").exists() else []:
            out.append(_read_json(p, {}))
        return out

    def seasons_done(self) -> list[int]:
        if not (self.dir / "seasons").exists():
            return []
        return sorted(int(p.parent.name) for p in (self.dir / "seasons").glob("*/scorecard.json"))

    # ---- track record ----
    def track_record(self) -> list[dict]:
        return _read_json(self.dir / "track_record.json", [])

    def append_track_record(self, row: dict) -> None:
        rows = [r for r in self.track_record() if r.get("season") != row.get("season")]
        rows.append(row)
        rows.sort(key=lambda r: r.get("season", 0))
        _write_json(self.dir / "track_record.json", rows)

    # ---- pending recommendations (approve mode) ----
    def pending(self) -> list[dict]:
        return _read_json(self.dir / "pending.json", [])

    def save_pending(self, items: list[dict]) -> None:
        _write_json(self.dir / "pending.json", items)

    @staticmethod
    def list_campaigns(root: str | Path = "runs") -> list[dict]:
        root = Path(root)
        out = []
        if not root.exists():
            return out
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "campaign.json").exists():
                s = RunStore(root, d.name)
                out.append({"id": d.name, "meta": s.meta(), "seasons_done": s.seasons_done(),
                            "track_record": s.track_record()})
        return out
