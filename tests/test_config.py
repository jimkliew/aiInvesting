import pytest

from aitrader.config import Params, Universe, load_universe


def test_params_ranges():
    p = Params.defaults()
    assert p.validate_set("desk.max_weight", 0.25) == 0.25
    assert p["desk.max_weight"] == 0.25
    with pytest.raises(ValueError):
        p.validate_set("desk.max_weight", 0.9)
    with pytest.raises(ValueError):
        p.validate_set("desk.rebalance", "daily")
    assert p.validate_set("research.rounds", 2.0) == 2 and isinstance(p["research.rounds"], int)
    with pytest.raises(ValueError):
        p.validate_set("cost_bps", 1)  # frozen, not a lever


def test_universe_default_and_quick(tmp_path):
    u = Universe()
    assert len(u.tickers) == 12 and u.benchmark == "SPY" and "SPY" in u.all_tickers
    q = Universe.quick()
    assert len(q.tickers) == 3 and q.seasons == 2
    y = tmp_path / "u.yaml"
    y.write_text("tickers: [AAPL, SPY]\nbenchmark: SPY\nseasons: 3\n")
    v = load_universe(y)
    assert v.seasons == 3 and v.all_tickers == ["AAPL", "SPY"]
