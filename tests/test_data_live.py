import pytest

from aitrader.data import fetch_prices


@pytest.mark.network
def test_fetch_spy(tmp_path):
    df = fetch_prices(["SPY"], start="2024-01-01", end="2024-03-01", cache_dir=tmp_path)
    assert len(df) > 30 and "SPY" in df.columns
    again = fetch_prices(["SPY"], start="2024-01-01", end="2024-03-01", cache_dir=tmp_path)
    assert len(again) == len(df)
