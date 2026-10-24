import numpy as np
import pandas as pd
import pytest


def make_prices(tickers=("AAPL", "MSFT", "NVDA", "SPY"), start="2023-01-02", days=520, seed=7):
    """Seeded random-walk closes on business days. Deterministic, no network."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=days)
    data = {}
    for i, t in enumerate(tickers):
        rets = rng.normal(0.0004 + 0.0002 * i, 0.012 + 0.004 * i, size=days)
        data[t] = 100.0 * (1 + i * 0.5) * np.cumprod(1 + rets)
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def prices():
    return make_prices()


@pytest.fixture
def tmp_runs(tmp_path):
    d = tmp_path / "runs"
    d.mkdir()
    return d
