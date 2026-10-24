"""Review Agent, the coach: assesses a season and recommends changes from the lever menu."""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import prompts
from ..schemas import SeasonReview


def _pct(x) -> str:
    try:
        return f"{float(x) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(x, nd=2) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "n/a"


def best_worst(decisions: list[dict], k: int = 3) -> list[dict]:
    """Decisions with a 1-month outcome, ranked by how well the call paid off."""
    scored = []
    for d in decisions:
        o = d.get("outcome_1m")
        if o is None:
            continue
        exposure = d.get("target_weight", 0.0)
        # a BUY/HOLD with weight gains when the stock rises; a SELL gains when it falls
        score = o if exposure > 0 else -o
        scored.append({**d, "score": score})
    scored.sort(key=lambda d: d["score"], reverse=True)
    best = [{**d, "tag": "best"} for d in scored[:k]]
    worst = [{**d, "tag": "worst"} for d in scored[-k:]] if len(scored) > k else []
    return best + worst


@dataclass
class ReviewPacket:
    season_label: str
    scorecard: dict
    track_record: list[dict]
    changelog: list[dict]
    notebook_summary: str
    best_worst: list[dict] = field(default_factory=list)
    lessons: dict[str, list[dict]] = field(default_factory=dict)

    def as_text(self) -> str:
        sc = self.scorecard
        lines = [f"SEASON {self.season_label} SCORECARD" + (" (partial quarter)" if sc.get("partial") else "")]
        for key in ("team", "book", "desk", "spy"):
            m = sc.get(key)
            if m:
                lines.append(f"- {key}: return {_pct(m.get('total_return'))}, Sharpe {_num(m.get('sharpe'))}, "
                             f"max drawdown {_pct(m.get('max_dd'))}, turnover {_num(m.get('turnover'), 1)}x/yr")
        if sc.get("book_name"):
            lines.append(f"- quant book was {sc['book_name']} (validation Sharpe {_num(sc.get('book_val_sharpe'))}"
                         + (", fallback" if sc.get("book_fallback") else "") + ")")
        for name, m in (sc.get("baselines") or {}).items():
            lines.append(f"- baseline {name}: return {_pct(m.get('total_return'))}, Sharpe {_num(m.get('sharpe'))}")
        lines.append("")
        lines.append("TRACK RECORD SO FAR (team vs SPY per season)")
        for r in self.track_record:
            lines.append(f"- S{r.get('season')} {r.get('label', '')}: team {_pct(r.get('team'))}, SPY {_pct(r.get('spy'))}, "
                         f"book {_pct(r.get('book'))}, desk {_pct(r.get('desk'))}, "
                         f"book val Sharpe {_num(r.get('book_val_sharpe'))} vs season Sharpe {_num(r.get('book_season_sharpe'))}")
        lines.append("")
        lines.append("CHANGES APPLIED SO FAR")
        if not self.changelog:
            lines.append("- none yet")
        for c in self.changelog:
            lines.append(f"- change {c['id']} before S{c.get('season', '?') + 1 if isinstance(c.get('season'), int) else '?'}: "
                         f"{c['lever']} {c.get('target', '')} -> {str(c.get('change', ''))[:120]} [{c.get('status', 'active')}]")
        lines.append("")
        lines.append("CURRENT LESSONS")
        any_l = False
        for agent, ls in self.lessons.items():
            for l in ls:
                any_l = True
                lines.append(f"- {agent} lesson {l['id']}: {l['text']}")
        if not any_l:
            lines.append("- none")
        lines.append("")
        lines.append("STRATEGY NOTEBOOK")
        lines.append(self.notebook_summary)
        lines.append("")
        lines.append("DESK: BEST AND WORST DECISIONS (1-month outcome after the call)")
        if not self.best_worst:
            lines.append("- no decisions with outcomes yet")
        for d in self.best_worst:
            lines.append(f"- [{d['tag']}] {d.get('date')} {d.get('ticker')} {d.get('action')} -> weight {d.get('target_weight')}, "
                         f"outcome {_pct(d.get('outcome_1m'))}: {str(d.get('reason', ''))[:140]}")
        return "\n".join(lines)


def coach(llm, packet: ReviewPacket, agent: str = "review") -> SeasonReview:
    system = prompts.load("review")
    return llm.structured(system, packet.as_text(), SeasonReview, agent=agent)
