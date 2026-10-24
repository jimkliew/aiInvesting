from __future__ import annotations

import math

import numpy as np

from ..schemas import Metrics
from .engine import Result

PERIODS = 252


def metrics(result: Result, periods: int = PERIODS) -> Metrics:
    pnl = result.pnl.astype(float)
    n = int(len(pnl))
    if n == 0:
        return Metrics(total_return=0, cagr=0, vol=0, sharpe=0, sortino=0, max_dd=0, calmar=0,
                       turnover=0, hit_rate=0, n_days=0)
    equity = result.equity
    total = float(equity.iloc[-1] - 1.0)
    years = n / periods
    cagr = float((1 + total) ** (1 / years) - 1) if years > 0 and (1 + total) > 0 else -1.0
    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    vol = std * math.sqrt(periods)
    sharpe = float(pnl.mean() / std * math.sqrt(periods)) if std > 0 else 0.0
    neg = pnl[pnl < 0]
    dstd = float(neg.std(ddof=1)) if len(neg) > 1 else 0.0
    sortino = float(pnl.mean() / dstd * math.sqrt(periods)) if dstd > 0 else 0.0
    dd = float((equity / equity.cummax() - 1.0).min())
    calmar = float(cagr / abs(dd)) if dd < 0 else 0.0
    active = pnl[pnl != 0]
    hit = float((active > 0).mean()) if len(active) else 0.0
    yrs = max(years, 1 / periods)
    return Metrics(
        total_return=round(total, 6), cagr=round(cagr, 6), vol=round(vol, 6), sharpe=round(sharpe, 4),
        sortino=round(sortino, 4), max_dd=round(dd, 6), calmar=round(calmar, 4),
        turnover=round(float(result.turnover) / yrs, 4),  # per year
        hit_rate=round(hit, 4), n_days=n,
    )


def clean_float(x: float) -> float:
    return 0.0 if x is None or not np.isfinite(x) else float(x)
