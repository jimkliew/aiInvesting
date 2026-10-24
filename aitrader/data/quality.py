"""Quality checks the Data Agent reads and acts on."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class QualityReport:
    ok: list[str] = field(default_factory=list)
    short: list[str] = field(default_factory=list)      # less than min_years of history
    gaps: dict[str, int] = field(default_factory=dict)  # internal missing days per ticker
    first_dates: dict[str, str] = field(default_factory=dict)
    last_date: str = ""
    n_days: int = 0

    def summary(self) -> str:
        lines = [f"{self.n_days} trading days, last date {self.last_date}."]
        lines.append(f"OK: {', '.join(self.ok) or 'none'}.")
        if self.short:
            lines.append("Short history (replace or drop): " + ", ".join(f"{t} (from {self.first_dates[t]})" for t in self.short) + ".")
        if self.gaps:
            lines.append("Internal gaps filled forward: " + ", ".join(f"{t} {n} days" for t, n in self.gaps.items()) + ".")
        return " ".join(lines)


def check_quality(prices: pd.DataFrame, min_years: float = 8.0) -> QualityReport:
    rep = QualityReport()
    if prices.empty:
        return rep
    last = prices.index.max()
    rep.last_date = str(last.date())
    rep.n_days = len(prices)
    for t in prices.columns:
        s = prices[t]
        first = s.first_valid_index()
        if first is None:
            rep.short.append(t)
            rep.first_dates[t] = "never"
            continue
        rep.first_dates[t] = str(first.date())
        inner = s.loc[first:]
        gaps = int(inner.isna().sum())
        if gaps:
            rep.gaps[t] = gaps
        years = (last - first).days / 365.25
        if years < min_years:
            rep.short.append(t)
        else:
            rep.ok.append(t)
    return rep


def clean(prices: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill internal gaps only; days before a listing stay NaN (weights there are 0)."""
    out = prices.copy()
    for t in out.columns:
        first = out[t].first_valid_index()
        if first is not None:
            out.loc[first:, t] = out.loc[first:, t].ffill()
    return out
