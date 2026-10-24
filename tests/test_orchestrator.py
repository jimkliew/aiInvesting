import json

import pytest

from aitrader.config import Universe
from aitrader.events import EventBus
from aitrader.orchestrator import Controls, Orchestrator
from aitrader.store import RunStore
from tests.conftest import make_prices
from tests.fakes import FakeLLM

SMA_CODE = (
    "def generate_signals(prices, features):\n"
    "    sig = (features['sma20'] > features['sma50']).astype(float)   # trend filter\n"
    "    sig['SPY'] = 0.0\n"
    "    w = sig.div(sig.sum(axis=1).replace(0, np.nan), axis=0)\n"
    "    return w.fillna(0.0)\n"
)


def default_responses(verdict="KEEP"):
    counter = {"n": 0}

    def gen(schema, system, user):
        name = schema.__name__
        if name == "Hypotheses":
            counter["n"] += 1
            return {"items": [{"name": f"sma_cross_{counter['n']}", "family": "trend", "idea": "sma20 over sma50",
                               "features_used": ["sma20", "sma50"], "why_it_might_work": "trend"}]}
        if name == "StrategyCode":
            return {"code": SMA_CODE, "notes": "simple"}
        if name == "Review":
            return {"verdict": verdict, "concerns": ["turnover"], "suggestion": "slower"}
        if name == "Decision":
            return {"action": "BUY", "target_weight": 0.2, "confidence": 0.6, "reason": "above the 50-day average"}
        if name == "SeasonReview":
            return {"assessment": "fine", "what_worked": "trend", "what_failed": "nothing",
                    "recommendations": [{"lever": "set_param", "target": "desk.max_weight", "change": "0.25",
                                         "rationale": "desk never fully invested", "expected_effect": "more exposure",
                                         "revert_if": "drawdown worsens"}]}
        raise AssertionError(f"unexpected schema {name}")

    return gen


def _run(tmp_path, llm, apply_mode="auto"):
    u = Universe(tickers=["AAPL", "MSFT", "NVDA"], benchmark="SPY", start="2023-01-02", campaign_start="2024-07-01", seasons=2)
    store = RunStore(tmp_path / "runs", "test")
    store.params["critic.min_val_sharpe"] = -5.0   # synthetic data: let any kept strategy qualify
    store.params["selector.max_turnover"] = 1e9     # random walks flip the SMA cross constantly
    store.save_params()
    bus = EventBus(store.path("trace.jsonl"))
    kinds = []
    bus.subscribe(lambda e: kinds.append(e.kind))
    orch = Orchestrator(u, store, llm, bus, Controls(), personas=["momentum"], apply_mode=apply_mode, quick=True,
                        data_dir=tmp_path / "data", use_llm_data=False)
    orch.run_campaign(2)
    return store, kinds


def test_quick_campaign_end_to_end(tmp_path, synthetic):
    llm = FakeLLM(default=default_responses())
    store, kinds = _run(tmp_path, llm)
    assert store.seasons_done() == [1, 2]
    tr = store.track_record()
    assert len(tr) == 2 and tr[1]["partial"] is True and tr[0]["book_name"].startswith("sma_cross")
    assert any(c["lever"] == "set_param" for c in store.changelog())
    assert store.params["desk.max_weight"] == 0.25
    n_dec = len(store.decisions(1))
    assert n_dec > 0 and n_dec % 3 == 0  # rebalance dates x 3 tickers x 1 persona
    assert all(d["outcome_1m"] is not None for d in store.decisions(1)[:3])
    assert store.reviews()[0]["assessment"] == "fine"
    for k in ("campaign_started", "data_ready", "hypotheses", "code", "sandbox_ok", "backtest", "critic", "book_selected",
              "decision", "fill", "season_scored", "review", "change_applied", "campaign_done"):
        assert k in kinds, k
    sc = store.scorecard(1)
    assert {"team", "book", "desk", "spy", "baselines", "daily"} <= set(sc)
    assert len(sc["daily"]) == sc["n_days"] > 50


def test_all_discard_falls_back(tmp_path, synthetic):
    llm = FakeLLM(default=default_responses(verdict="DISCARD"))
    store, kinds = _run(tmp_path, llm)
    # nothing researched qualified, so a classic baseline wins on validation and the page says so
    assert "selector_note" in kinds and "selector_fallback" not in kinds
    from aitrader.backtest.strategies import BASELINES
    assert store.quant_book(1)["name"] in BASELINES and not store.quant_book(1)["code"]
    assert store.seasons_done() == [1, 2]


def test_approve_mode_queues_recommendations(tmp_path, synthetic):
    llm = FakeLLM(default=default_responses())
    store, kinds = _run(tmp_path, llm, apply_mode="approve")
    assert store.changelog() == [] and len(store.pending()) == 2 and "pending_recommendations" in kinds


def test_stop_between_turns(tmp_path, synthetic):
    controls = Controls()
    calls = {"n": 0}
    base = default_responses()

    def gen(schema, system, user):
        calls["n"] += 1
        if calls["n"] == 3:
            controls.stop()
        return base(schema, system, user)

    u = Universe(tickers=["AAPL", "MSFT", "NVDA"], benchmark="SPY", start="2023-01-02", campaign_start="2024-07-01", seasons=2)
    store = RunStore(tmp_path / "runs", "stop")
    bus = EventBus(store.path("trace.jsonl"))
    kinds = []
    bus.subscribe(lambda e: kinds.append(e.kind))
    orch = Orchestrator(u, store, FakeLLM(default=gen), bus, controls, quick=True, data_dir=tmp_path / "data", use_llm_data=False)
    orch.run_campaign(2)
    assert "stopped" in kinds and store.seasons_done() == []


def test_data_agent_refuses_to_replace_healthy_tickers(tmp_path, synthetic):
    from aitrader.agents.data_agent import run_data_agent
    from aitrader.config import Universe
    u = Universe(tickers=["AAPL", "MSFT", "NVDA"], benchmark="SPY", start="2023-01-02")
    script = [("tool", "fetch_prices", {"tickers": ["AAPL", "MSFT", "NVDA"]}), ("tool", "check_quality", {}),
              ("tool", "replace_ticker", {"bad": "AAPL", "replacement": "CSCO"}), ("tool", "write_report", {"text": "done"}), ("final", "done")]
    llm = FakeLLM([script])
    res = run_data_agent(llm, u, None, tmp_path / "data", use_llm=True)
    assert sorted(res.tickers) == ["AAPL", "MSFT", "NVDA"]      # the swap was refused
    assert res.tool_calls == ["fetch_prices", "check_quality", "replace_ticker", "write_report"]
