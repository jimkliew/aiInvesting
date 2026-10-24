"""Baseline strategies. Same interface the Coder Agent must satisfy:

    def generate_signals(prices, features) -> weights in [0, 1], date x ticker

The benchmark column (SPY) is never traded by the team; `tradeable()` drops it.
"""
from __future__ import annotations

import pandas as pd

BENCHMARK = "SPY"


def tradeable(prices: pd.DataFrame) -> list[str]:
    return [c for c in prices.columns if c != BENCHMARK]


def _zeros(prices: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(0.0, index=prices.index, columns=prices.columns)


def _row_normalise(w: pd.DataFrame) -> pd.DataFrame:
    s = w.sum(axis=1)
    return w.div(s.where(s > 0, 1.0), axis=0)


def buy_hold_spy(prices, features):
    w = _zeros(prices)
    if BENCHMARK in w.columns:
        w[BENCHMARK] = 1.0
    else:
        w[:] = 1.0 / len(w.columns)
    return w


def equal_weight(prices, features):
    w = _zeros(prices)
    cols = tradeable(prices)
    w[cols] = prices[cols].notna().astype(float)
    return _row_normalise(w)


def sma_cross_50_200(prices, features):
    cols = tradeable(prices)
    sig = (features["sma50"][cols] > features["sma200"][cols]).astype(float)
    w = _zeros(prices)
    w[cols] = _row_normalise(sig)
    return w


def momentum_12_1(prices, features, top_n: int = 3):
    cols = tradeable(prices)
    m = features["mom_12_1"][cols]
    rank = m.rank(axis=1, ascending=False)
    sig = (rank <= top_n).astype(float).where(m.notna(), 0.0)
    w = _zeros(prices)
    w[cols] = _row_normalise(sig)
    return w


def rsi_meanrev(prices, features, enter: float = 30.0, exit_: float = 55.0):
    cols = tradeable(prices)
    r = features["rsi14"][cols]
    entry = r < enter
    leave = r > exit_
    state = entry.where(entry | leave).ffill().fillna(False).astype(bool)
    w = _zeros(prices)
    w[cols] = _row_normalise(state.astype(float))
    return w


BASELINES = {
    "buy_hold_spy": buy_hold_spy,
    "equal_weight": equal_weight,
    "sma_cross_50_200": sma_cross_50_200,
    "momentum_12_1": momentum_12_1,
    "rsi_meanrev": rsi_meanrev,
}
