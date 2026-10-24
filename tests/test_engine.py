import numpy as np
import pandas as pd

from aitrader.backtest import BASELINES, metrics, normalise, run
from aitrader.data import compute_features


def test_five_bar_hand_example():
    idx = pd.bdate_range("2024-01-01", periods=5)
    prices = pd.DataFrame({"A": [100.0, 110.0, 99.0, 99.0, 108.9]}, index=idx)
    # decide 100% long at the close of bar 0, go flat at the close of bar 2
    weights = pd.DataFrame({"A": [1.0, 1.0, 0.0, 0.0, 0.0]}, index=idx)
    r = run(weights, prices, cost_bps=5)
    expected = [1.0, 1.0995, 0.98955, 0.98955 * (1 - 0.0005), 0.98955 * (1 - 0.0005)]
    assert np.allclose(r.equity.values, expected, atol=1e-9)
    assert abs(r.turnover - 2.0) < 1e-12
    assert list(r.weights["A"]) == [0.0, 1.0, 1.0, 0.0, 0.0]


def test_normalise_clips_and_scales():
    w = pd.DataFrame({"A": [0.8, -0.2], "B": [0.8, 0.5]})
    n = normalise(w)
    assert np.allclose(n.iloc[0].values, [0.5, 0.5])
    assert np.allclose(n.iloc[1].values, [0.0, 0.5])


def test_metrics_on_steady_gain():
    idx = pd.bdate_range("2024-01-01", periods=100)
    prices = pd.DataFrame({"A": 100 * 1.01 ** np.arange(100)}, index=idx)
    r = run(pd.DataFrame({"A": 1.0}, index=idx), prices, cost_bps=0)
    m = metrics(r)
    assert m.max_dd == 0 and m.hit_rate == 1.0 and m.total_return > 1.5 and m.sharpe > 0


def test_baselines_respect_interface(prices):
    f = compute_features(prices)
    for name, fn in BASELINES.items():
        w = fn(prices, f)
        assert w.shape == prices.shape, name
        assert (w.fillna(0) >= 0).all().all() and (w.fillna(0).sum(axis=1) <= 1 + 1e-9).all(), name
        if name != "buy_hold_spy":
            assert (w["SPY"].fillna(0) == 0).all(), f"{name} must not hold the benchmark"
        r = run(w.fillna(0), prices)
        assert r.equity.iloc[-1] > 0
