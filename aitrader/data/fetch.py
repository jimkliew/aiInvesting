"""Daily adjusted closes from yfinance, cached as parquet per ticker.

Free and keyless. yfinance is an unofficial interface to Yahoo Finance; use it
for personal and educational purposes and expect the occasional gap.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd


def _download(ticker: str, start: str, end: str | None, retries: int = 3) -> pd.Series:
    import yfinance as yf  # imported lazily so tests without network never touch it

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True, threads=False)
            if df is None or df.empty:
                raise RuntimeError(f"no data returned for {ticker}")
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna().astype(float)
            close.index = pd.to_datetime(close.index).tz_localize(None)
            close.name = ticker
            return close
        except Exception as e:  # network hiccups, rate limits
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"could not fetch {ticker}: {last_err}")


def fetch_prices(
    tickers: list[str],
    start: str = "2015-01-01",
    end: str | None = None,
    cache_dir: str | Path = "data/raw",
    refresh: bool = False,
    on_ticker=None,
) -> pd.DataFrame:
    """Return a date x ticker DataFrame of adjusted closes. Serves from cache when fresh."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    target_end = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
    frames: dict[str, pd.Series] = {}
    for t in tickers:
        p = cache / f"{t}.parquet"
        s: pd.Series | None = None
        if p.exists() and not refresh:
            cached = pd.read_parquet(p)["close"]
            cached.index = pd.to_datetime(cached.index)
            if len(cached) and (target_end - cached.index.max()).days <= 4:
                s = cached
        if s is None:
            s = _download(t, start, end)
            s.to_frame("close").to_parquet(p)
            if on_ticker:
                on_ticker(t, len(s), "fetched")
        elif on_ticker:
            on_ticker(t, len(s), "cached")
        frames[t] = s
    df = pd.DataFrame(frames).sort_index()
    df.index.name = "date"
    df = df.loc[pd.Timestamp(start):]
    if end:
        df = df.loc[:pd.Timestamp(end)]
    return df
