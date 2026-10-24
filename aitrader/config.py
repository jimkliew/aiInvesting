"""Universe and lever-adjustable parameters.

The universe (tickers, benchmark, costs, season calendar) is frozen for a
campaign. Params are the only knobs the Review Agent may turn, each inside a
hard range (practice P17).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META",
    "TSLA", "AVGO", "AMD", "CRM", "ORCL", "NFLX",
]
QUICK_TICKERS = ["AAPL", "MSFT", "NVDA"]


@dataclass
class Universe:
    tickers: list[str] = field(default_factory=lambda: list(DEFAULT_TICKERS))
    benchmark: str = "SPY"
    start: str = "2015-01-01"
    cost_bps: float = 5.0
    campaign_start: str = "2025-01-01"
    seasons: int = 6

    @property
    def all_tickers(self) -> list[str]:
        return [*self.tickers, self.benchmark] if self.benchmark not in self.tickers else list(self.tickers)

    @classmethod
    def quick(cls) -> "Universe":
        return cls(tickers=list(QUICK_TICKERS), seasons=2)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_universe(path: str | Path = "universe.yaml") -> Universe:
    p = Path(path)
    if not p.exists():
        return Universe()
    with open(p) as f:
        d = yaml.safe_load(f) or {}
    return Universe(**{k: v for k, v in d.items() if k in Universe.__dataclass_fields__})


# Allowed ranges for set_param. Tuples are (min, max); sets are choices.
RANGES: dict[str, Any] = {
    "desk.max_weight": (0.10, 0.40),
    "critic.min_val_sharpe": (0.30, 1.00),
    "research.rounds": (1, 3),
    "research.ideas_per_round": (1, 6),
    "desk.rebalance": {"weekly", "monthly"},
    "book.rebalance": {"daily", "weekly", "monthly"},
    "selector.max_turnover": (50, 600),
}

DEFAULT_PARAMS: dict[str, Any] = {
    "desk.max_weight": 0.30,
    "critic.min_val_sharpe": 0.50,
    "research.rounds": 1,
    "research.ideas_per_round": 4,
    "desk.rebalance": "monthly",
    "book.rebalance": "weekly",
    "selector.max_turnover": 300,
    "family_focus": {"emphasise": [], "avoid": []},
    "budget.max_llm_calls": 120,
    "budget.max_minutes": 20,
    "budget.max_strategies": 8,
}


class Params(dict):
    """A dict with range-checked assignment for the lever-adjustable keys."""

    @classmethod
    def defaults(cls) -> "Params":
        return cls({k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_PARAMS.items()})

    def validate_set(self, name: str, value: Any) -> Any:
        if name not in RANGES:
            raise ValueError(f"{name} is not an adjustable parameter; allowed: {sorted(RANGES)}")
        rng = RANGES[name]
        if isinstance(rng, set):
            if value not in rng:
                raise ValueError(f"{name} must be one of {sorted(rng)}, got {value!r}")
            self[name] = value
            return value
        lo, hi = rng
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a number between {lo} and {hi}, got {value!r}")
        if not (lo <= v <= hi):
            raise ValueError(f"{name} must be between {lo} and {hi}, got {v}")
        if isinstance(DEFAULT_PARAMS[name], int):
            v = int(round(v))
        self[name] = v
        return v
