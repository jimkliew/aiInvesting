import pytest

from aitrader.backtest.lookahead import lookahead_check
from aitrader.backtest.sandbox import Rejected, check_source, run_strategy
from aitrader.data import compute_features

BREAKOUT = '''
def generate_signals(prices, features):
    high20 = features["high20"]
    sma20 = features["sma20"]
    entry = prices > high20
    exit_ = prices < sma20
    held = entry.where(entry | exit_).ffill().fillna(False).astype(bool)
    vol = features["vol20"].replace(0, np.nan)
    raw = held.astype(float) / vol
    raw["SPY"] = 0.0
    w = raw.div(raw.sum(axis=1).replace(0, np.nan), axis=0)
    return w.clip(upper=0.30).fillna(0.0)
'''


@pytest.mark.parametrize("code,needle", [
    ("import os\ndef generate_signals(prices, features): return prices", "imports"),
    ("def generate_signals(prices, features):\n    open('x')\n    return prices", "open"),
    ("def generate_signals(prices, features):\n    return prices.shift(-1)", "future"),
    ("def generate_signals(prices, features):\n    return prices.shift(periods=-2)", "future"),
    ("def generate_signals(prices, features):\n    return prices.__class__", "attribute"),
    ("def other(prices, features):\n    return prices", "must define"),
    ("def generate_signals(prices, features)\n    return prices", "syntax"),
])
def test_check_source_rejects(code, needle):
    with pytest.raises(Rejected) as e:
        check_source(code)
    assert needle in str(e.value)


def test_run_breakout_in_subprocess(prices):
    f = compute_features(prices)
    w = run_strategy(BREAKOUT, prices, f, timeout=30)
    assert w.shape == prices.shape and (w >= 0).all().all() and (w.sum(axis=1) <= 1 + 1e-9).all()
    assert (w["SPY"] == 0).all()
    assert w.abs().sum().sum() > 0


def test_runtime_error_is_rejected(prices):
    code = "def generate_signals(prices, features):\n    x = 1 / 0\n    return prices"
    with pytest.raises(Rejected) as e:
        run_strategy(code, prices, compute_features(prices))
    assert "ZeroDivisionError" in str(e.value)


def test_timeout_is_rejected(prices):
    code = "def generate_signals(prices, features):\n    while True:\n        pass\n    return prices"
    with pytest.raises(Rejected) as e:
        run_strategy(code, prices, compute_features(prices), timeout=4)
    assert "timed out" in str(e.value)


def test_lookahead_catches_reversed_rolling(prices):
    f = compute_features(prices)
    peek = ("def generate_signals(prices, features):\n"
            "    fut = prices[::-1].rolling(5).mean()[::-1]\n"
            "    w = (fut > prices).astype(float)\n"
            "    w['SPY'] = 0.0\n"
            "    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)\n")
    ok, msg, _ = lookahead_check(peek, prices, f, cut=30, timeout=30)
    assert not ok and "future" in msg


def test_lookahead_passes_causal_code(prices):
    f = compute_features(prices)
    ok, msg, full = lookahead_check(BREAKOUT, prices, f, cut=30, timeout=30)
    assert ok, msg
    assert full.shape == prices.shape
