"""Season scoring: quant book, desk, team (half each), SPY and baselines. Deterministic."""
from __future__ import annotations

import pandas as pd

from ..data.features import slice_to
from ..schemas import Metrics
from .engine import Result, run
from .metrics import metrics
from .strategies import BASELINES


def window_result(weights: pd.DataFrame, prices: pd.DataFrame, start, end, cost_bps: float) -> Result:
    """Run on history up to `end` so the lag is honoured, then keep the [start, end] window."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    sub = prices.loc[:end]
    r = run(weights.reindex(index=sub.index, columns=sub.columns).fillna(0.0), sub, cost_bps)
    mask = (r.pnl.index >= start) & (r.pnl.index <= end)
    pnl = r.pnl[mask]
    held = r.weights[mask]
    dw = held.diff()
    if len(held):
        dw.iloc[0] = held.iloc[0] - (r.weights.shift(1)[mask].iloc[0] if mask.any() else 0)
    turnover = float(dw.abs().sum().sum()) if len(held) else 0.0
    equity = (1.0 + pnl).cumprod()
    return Result(equity=equity, pnl=pnl, weights=held, turnover=turnover, cost=r.cost[mask])


def window_metrics(weights: pd.DataFrame, prices: pd.DataFrame, start, end, cost_bps: float) -> Metrics:
    return metrics(window_result(weights, prices, start, end, cost_bps))


def _series_from_pnl(pnl: pd.Series) -> pd.Series:
    return (1.0 + pnl).cumprod()


def score_season(prices: pd.DataFrame, features: dict[str, pd.DataFrame], season, book_weights: pd.DataFrame,
                 desk_weights: pd.DataFrame, cost_bps: float, benchmark: str = "SPY", book_info: dict | None = None) -> dict:
    start, end = season.start, season.end
    book = window_result(book_weights, prices, start, end, cost_bps)
    desk = window_result(desk_weights, prices, start, end, cost_bps)
    team_pnl = 0.5 * book.pnl + 0.5 * desk.pnl
    team = Result(equity=_series_from_pnl(team_pnl), pnl=team_pnl, weights=0.5 * book.weights + 0.5 * desk.weights,
                  turnover=0.5 * (book.turnover + desk.turnover), cost=0.5 * (book.cost + desk.cost))
    spy_pnl = prices[benchmark].pct_change().loc[start:end].fillna(0.0)
    spy = Result(equity=_series_from_pnl(spy_pnl), pnl=spy_pnl, weights=pd.DataFrame(), turnover=0.0, cost=spy_pnl * 0)

    sub_prices = prices.loc[:end]
    sub_feats = slice_to(features, end)
    baselines: dict[str, dict] = {}
    base_results: dict[str, Result] = {}
    for name, fn in BASELINES.items():
        try:
            w = fn(sub_prices, sub_feats).fillna(0.0)
            r = window_result(w, prices, start, end, cost_bps)
            baselines[name] = metrics(r).model_dump()
            base_results[name] = r
        except Exception as e:  # a broken baseline must not stop scoring
            baselines[name] = {"error": str(e)}

    daily = pd.DataFrame({"team": team.equity, "book": book.equity, "desk": desk.equity, "spy": spy.equity})
    for name, r in base_results.items():
        daily[name] = r.equity
    daily_rows = [{"date": str(d.date()), **{k: round(float(v), 6) for k, v in row.items()}} for d, row in daily.iterrows()]

    m_book, m_desk, m_team, m_spy = metrics(book), metrics(desk), metrics(team), metrics(spy)
    info = book_info or {}
    return {
        "season": season.n, "label": season.label, "start": str(start.date()), "end": str(end.date()),
        "partial": bool(getattr(season, "partial", False)), "n_days": int(len(team_pnl)),
        "team": m_team.model_dump(), "book": m_book.model_dump(), "desk": m_desk.model_dump(), "spy": m_spy.model_dump(),
        "baselines": baselines, "daily": daily_rows,
        "book_name": info.get("name"), "book_val_sharpe": info.get("val_sharpe"), "book_fallback": info.get("fallback", False),
    }
