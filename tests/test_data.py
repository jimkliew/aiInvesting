import numpy as np
import pandas as pd

from aitrader.data import check_quality, compute_features, feature_catalog, snapshot, write_manifest
from aitrader.data.manifest import prices_hash
from aitrader.data.quality import clean


def test_features_known_values(prices):
    f = compute_features(prices)
    assert set(f) >= {"ret_1d", "sma20", "sma50", "sma200", "rsi14", "vol20", "mom_12_1", "high20", "drawdown"}
    for v in f.values():
        assert v.shape == prices.shape
    const = pd.DataFrame({"X": np.full(60, 50.0)}, index=pd.bdate_range("2024-01-01", periods=60))
    fc = compute_features(const)
    assert abs(fc["sma20"]["X"].iloc[-1] - 50.0) < 1e-12
    rising = pd.DataFrame({"X": np.arange(1, 61, dtype=float)}, index=const.index)
    assert compute_features(rising)["rsi14"]["X"].iloc[-1] == 100.0
    assert "high20" in feature_catalog()


def test_snapshot_uses_only_past(prices):
    f = compute_features(prices)
    as_of = prices.index[300]
    text = snapshot(prices, f, "AAPL", as_of, current_weight=0.2, max_weight=0.3)
    assert f"as_of: {as_of.date()}" in text
    assert f"{prices['AAPL'].iloc[300]:.2f}" in text
    assert f"{prices['AAPL'].iloc[301]:.2f}" not in text.split("closes_20d")[1].split("\n")[0]
    assert "max_weight: 0.30" in text


def test_quality_flags_short_history(prices):
    p = prices.copy()
    p.loc[: p.index[400], "NVDA"] = np.nan  # listed late
    p.loc[p.index[10], "AAPL"] = np.nan      # one internal gap
    rep = check_quality(p, min_years=1.0)
    assert "NVDA" in rep.short and "AAPL" in rep.ok
    assert rep.gaps == {"AAPL": 1}
    cleaned = clean(p)
    assert not cleaned["AAPL"].isna().any()
    assert cleaned["NVDA"].iloc[0] != cleaned["NVDA"].iloc[0]  # still NaN before listing


def test_manifest_hash_stable(prices, tmp_path):
    m1 = write_manifest(prices, tmp_path / "m.json", notes="t")
    m2 = write_manifest(prices, tmp_path / "m2.json")
    assert m1["sha256"] == m2["sha256"] == prices_hash(prices)
    assert m1["rows"] == len(prices) and m1["tickers"] == list(prices.columns)
