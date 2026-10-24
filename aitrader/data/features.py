"""Indicators shared by strategies and the trader's snapshot.

Every feature is a date x ticker DataFrame computed from past data only.
`snapshot()` is the only thing a trader persona ever sees (practice P6: as-of).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES: dict[str, str] = {
    "ret_1d": "daily simple return, close to close",
    "sma20": "20-day simple moving average of close",
    "sma50": "50-day simple moving average of close",
    "sma200": "200-day simple moving average of close",
    "rsi14": "14-day RSI (Wilder), 0 to 100",
    "vol20": "20-day realised volatility of daily returns, annualised",
    "mom_12_1": "12-month return skipping the most recent month",
    "high20": "highest close of the previous 20 days, shifted one day (today excluded)",
    "drawdown": "close divided by running maximum close, minus one",
}


def rsi(prices: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    delta = prices.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    roll_down = down.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = roll_up / roll_down.replace(0.0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(~(roll_down == 0), 100.0)
    out = out.where(~((roll_down == 0) & (roll_up == 0)), 50.0)
    return out


def compute_features(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ret = prices.pct_change()
    return {
        "ret_1d": ret,
        "sma20": prices.rolling(20).mean(),
        "sma50": prices.rolling(50).mean(),
        "sma200": prices.rolling(200).mean(),
        "rsi14": rsi(prices, 14),
        "vol20": ret.rolling(20).std() * np.sqrt(252),
        "mom_12_1": prices.shift(21) / prices.shift(252) - 1,
        "high20": prices.rolling(20).max().shift(1),
        "drawdown": prices / prices.cummax() - 1,
    }


def feature_catalog() -> str:
    lines = ['features is a dict of date x ticker DataFrames aligned with prices:']
    for k, v in FEATURES.items():
        lines.append(f'  features["{k}"]: {v}')
    return "\n".join(lines)


def slice_to(frames: dict[str, pd.DataFrame], end) -> dict[str, pd.DataFrame]:
    end = pd.Timestamp(end)
    return {k: v.loc[:end] for k, v in frames.items()}


def _ret(px: pd.Series, days: int) -> float | None:
    if len(px) <= days:
        return None
    return float(px.iloc[-1] / px.iloc[-1 - days] - 1)


def _pct(x: float | None) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:+.1f}%"


def snapshot(
    prices: pd.DataFrame,
    features: dict[str, pd.DataFrame],
    ticker: str,
    as_of,
    current_weight: float,
    max_weight: float,
) -> str:
    """About 300 tokens of text. Uses only rows at or before as_of."""
    as_of = pd.Timestamp(as_of)
    px = prices[ticker].loc[:as_of].dropna()
    if px.empty:
        raise ValueError(f"no prices for {ticker} up to {as_of.date()}")
    last = float(px.iloc[-1])

    def f(name):
        s = features[name][ticker].loc[:as_of].dropna()
        return float(s.iloc[-1]) if len(s) else None

    def vs(name):
        v = f(name)
        return "n/a" if v is None or v == 0 else f"{(last / v - 1) * 100:+.1f}%"

    closes = " ".join(f"{c:.2f}" for c in px.tail(20).tolist())
    rsi_v = f("rsi14")
    vol_v = f("vol20")
    return "\n".join([
        f"ticker: {ticker}   as_of: {px.index[-1].date()}   last_close: {last:.2f}",
        f"closes_20d: {closes}",
        f"vs_sma20: {vs('sma20')}  vs_sma50: {vs('sma50')}  vs_sma200: {vs('sma200')}",
        f"rsi14: {'n/a' if rsi_v is None else f'{rsi_v:.0f}'}   "
        f"ret_1m: {_pct(_ret(px, 21))}  ret_3m: {_pct(_ret(px, 63))}  ret_12m: {_pct(_ret(px, 252))}",
        f"vol_20d_ann: {'n/a' if vol_v is None else f'{vol_v * 100:.0f}%'}   "
        f"current_weight: {current_weight:.2f}   max_weight: {max_weight:.2f}",
    ])
