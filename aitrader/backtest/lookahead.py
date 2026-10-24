"""Lookahead guard (practice P6): a strategy's past signals must not change when the future is withheld."""
from __future__ import annotations

import pandas as pd

from .sandbox import run_strategy


def lookahead_check(code: str, prices: pd.DataFrame, features: dict[str, pd.DataFrame], cut: int = 60,
                    timeout: float = 20, tol: float = 1e-9) -> tuple[bool, str, pd.DataFrame]:
    """Returns (passes, message, full_weights)."""
    full = run_strategy(code, prices, features, timeout=timeout)
    short_prices = prices.iloc[:-cut]
    short_feats = {k: v.iloc[:-cut] for k, v in features.items()}
    part = run_strategy(code, short_prices, short_feats, timeout=timeout)
    overlap = full.loc[part.index]
    diff = float((overlap - part).abs().max().max())
    if pd.isna(diff):
        diff = 0.0
    ok = diff <= tol
    msg = (f"signals identical when the last {cut} days were withheld" if ok
           else f"signals changed by up to {diff:.3g} when the last {cut} days were withheld: the code uses future data")
    return ok, msg, full
