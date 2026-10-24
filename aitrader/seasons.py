"""Season calendar: rolling out-of-sample quarters (practice P16).

For a season starting at T: train = data_start .. T-12m-1d, validation = the 12
months before T, season = the quarter from T. Agents only ever see data up to
the validation end until the season has been traded.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd


@dataclass(frozen=True)
class Season:
    n: int
    start: pd.Timestamp
    end: pd.Timestamp
    train: tuple[pd.Timestamp, pd.Timestamp]
    validation: tuple[pd.Timestamp, pd.Timestamp]
    partial: bool = False

    @property
    def label(self) -> str:
        return f"{self.start.year} Q{(self.start.month - 1) // 3 + 1}"

    @property
    def visible_end(self) -> pd.Timestamp:
        """Last date any agent may see before the season is traded."""
        return self.validation[1]

    def to_dict(self) -> dict:
        d = lambda t: str(pd.Timestamp(t).date())
        return {
            "n": self.n, "label": self.label, "start": d(self.start), "end": d(self.end),
            "train": [d(self.train[0]), d(self.train[1])],
            "validation": [d(self.validation[0]), d(self.validation[1])],
            "partial": self.partial,
        }


def calendar(campaign_start: str = "2025-01-01", n_seasons: int = 6, data_start: str = "2015-01-01") -> list[Season]:
    start = pd.Timestamp(campaign_start)
    out: list[Season] = []
    for i in range(n_seasons):
        s = start + pd.DateOffset(months=3 * i)
        e = s + pd.DateOffset(months=3) - pd.Timedelta(days=1)
        v0 = s - pd.DateOffset(months=12)
        v1 = s - pd.Timedelta(days=1)
        out.append(Season(n=i + 1, start=s, end=e, train=(pd.Timestamp(data_start), v0 - pd.Timedelta(days=1)),
                          validation=(v0, v1)))
    return out


def trim_to_data(season: Season, last_date) -> Season:
    last = pd.Timestamp(last_date)
    if season.end > last:
        return replace(season, end=last, partial=True)
    return season


def rebalance_dates(index: pd.DatetimeIndex, start, end, cadence: str = "weekly") -> list[pd.Timestamp]:
    """First trading day of each week (or month) inside [start, end]."""
    idx = index[(index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))]
    if len(idx) == 0:
        return []
    s = pd.Series(idx, index=idx)
    if cadence == "monthly":
        key = idx.to_period("M")
    else:
        iso = idx.isocalendar()
        key = iso["year"].astype(str) + "-" + iso["week"].astype(str)
    return list(s.groupby(key.values).first().sort_values())
