"""Critic Agent: KEEP or DISCARD from train and validation metrics. Never sees the season."""
from __future__ import annotations

from .. import prompts
from ..schemas import Metrics, Review


def fmt_metrics(m: Metrics | dict | None) -> str:
    if m is None:
        return "n/a"
    d = m if isinstance(m, dict) else m.model_dump()
    return (f"Sharpe {d['sharpe']:.2f}, total return {d['total_return'] * 100:+.1f}%, "
            f"max drawdown {d['max_dd'] * 100:.1f}%, turnover {d['turnover'] * 100:.0f}%/yr, "
            f"hit rate {d['hit_rate'] * 100:.0f}%, {d['n_days']} days")


def review(llm, code: str, m_train, m_val, notebook_summary: str, lessons: list[str] | None,
           min_val_sharpe: float, max_turnover: float, agent: str = "critic") -> Review:
    system = prompts.load("critic", lessons=lessons, min_val_sharpe=min_val_sharpe, max_turnover=int(max_turnover))
    user = (f"Code:\n{code}\n\nTraining window: {fmt_metrics(m_train)}\n"
            f"Validation window: {fmt_metrics(m_val)}\n\nLab notebook:\n{notebook_summary}")
    return llm.structured(system, user, Review, agent=agent)
