"""Vectorised backtest engine.

A weight decided at tonight's close is held from tomorrow (one-bar lag).
Cost is cost_bps on every unit of weight that changes. Long only, no leverage:
weights are clipped to [0, 1] and rows summing above 1 are scaled down.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Result:
    equity: pd.Series      # growth of 1.0
    pnl: pd.Series         # daily portfolio return after cost
    weights: pd.DataFrame  # weights actually held each day (after the lag)
    turnover: float        # sum of |weight changes| over the window
    cost: pd.Series        # daily cost drag


def normalise(weights: pd.DataFrame) -> pd.DataFrame:
    w = weights.astype(float).clip(lower=0.0, upper=1.0).fillna(0.0)
    s = w.sum(axis=1)
    scale = s.where(s > 1.0, 1.0)
    return w.div(scale, axis=0)


def run(weights: pd.DataFrame, prices: pd.DataFrame, cost_bps: float = 5.0) -> Result:
    w = normalise(weights).reindex(index=prices.index, columns=prices.columns).fillna(0.0)
    held = w.shift(1).fillna(0.0)                       # one-bar lag
    ret = prices.pct_change().fillna(0.0)
    held = held.where(prices.notna(), 0.0)              # nothing held where there is no price
    dw = held.diff()
    dw.iloc[0] = held.iloc[0]
    turn = dw.abs().sum(axis=1)
    cost = cost_bps / 1e4 * turn
    pnl = (held * ret).sum(axis=1) - cost
    equity = (1.0 + pnl).cumprod()
    return Result(equity=equity, pnl=pnl, weights=held, turnover=float(turn.sum()), cost=cost)
