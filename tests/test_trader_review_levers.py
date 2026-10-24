import json

import pytest

from aitrader.agents.review_agent import ReviewPacket, best_worst, coach
from aitrader.agents.trader_agent import decide
from aitrader.levers import InvalidLever, apply, parse_focus, revert
from aitrader.schemas import Recommendation
from aitrader.store import RunStore
from tests.fakes import FakeLLM


def test_decide_clamps_and_normalises_action():
    llm = FakeLLM([json.dumps({"action": "HOLD", "target_weight": 0.9, "confidence": 1.4, "reason": "r"})])
    d = decide(llm, "momentum", "snapshot", None, max_weight=0.3, current_weight=0.2)
    assert d.action == "HOLD" and d.target_weight == 0.2 and d.confidence == 1.0
    llm = FakeLLM([json.dumps({"action": "BUY", "target_weight": 25, "confidence": 0.5, "reason": "r"})])
    d = decide(llm, "contrarian", "snapshot", ["1. (after S1) x"], max_weight=0.3, current_weight=0.0)
    # 25 means 25 percent
    assert d.target_weight == 0.25 and d.action == "BUY"
    assert "Lessons from the coach" in llm.log[0]["system"]
    llm = FakeLLM([json.dumps({"action": "BUY", "target_weight": 0.0, "confidence": 0.5, "reason": "r"})])
    assert decide(llm, "risk_averse", "s", None, 0.3, 0.2).action == "SELL"


def test_best_worst_ranking():
    ds = [{"date": "d1", "ticker": "A", "action": "BUY", "target_weight": 0.2, "outcome_1m": 0.10, "reason": ""},
          {"date": "d2", "ticker": "B", "action": "SELL", "target_weight": 0.0, "outcome_1m": -0.08, "reason": ""},
          {"date": "d3", "ticker": "C", "action": "BUY", "target_weight": 0.2, "outcome_1m": -0.12, "reason": ""},
          {"date": "d4", "ticker": "D", "action": "HOLD", "target_weight": 0.1, "outcome_1m": None, "reason": ""}]
    bw = best_worst(ds, k=1)
    assert bw[0]["ticker"] == "A" and bw[0]["tag"] == "best"
    assert bw[-1]["ticker"] == "C" and bw[-1]["tag"] == "worst"


def test_coach_packet_and_parse():
    packet = ReviewPacket("2025 Q1", {"team": {"total_return": 0.01, "sharpe": 0.5, "max_dd": -0.03, "turnover": 2.0},
                                      "spy": {"total_return": -0.04, "sharpe": -0.3, "max_dd": -0.1, "turnover": 0},
                                      "book_name": "sma_cross", "book_val_sharpe": 1.4},
                          [{"season": 1, "label": "2025 Q1", "team": 0.01, "spy": -0.04}], [], "(empty)", [], {})
    text = packet.as_text()
    assert "team: return +1.0%" in text and "quant book was sma_cross" in text
    llm = FakeLLM([json.dumps({"assessment": "a", "what_worked": "w", "what_failed": "f",
                               "recommendations": [{"lever": "set_param", "target": "desk.max_weight", "change": "0.25",
                                                    "rationale": "r", "expected_effect": "e", "revert_if": "x"}]})])
    r = coach(llm, packet)
    assert r.recommendations[0].lever == "set_param"


def test_levers_apply_and_revert(tmp_runs):
    st = RunStore(tmp_runs, "c")
    st.notebook_add({"name": "sma_cross", "family": "trend", "status": "kept", "season": 1})
    rec = Recommendation(lever="add_lesson", target="Trader momentum", change="If RSI14 > 75, do not add.", rationale="r")
    c1 = apply(st, rec, season=1)
    assert c1["id"] == 1 and st.lessons("trader_momentum")[0]["text"].startswith("If RSI14")
    with pytest.raises(InvalidLever):
        apply(st, Recommendation(lever="add_lesson", target="trader_momentum", change="x" * 301, rationale="r"), 1)
    with pytest.raises(InvalidLever):
        apply(st, Recommendation(lever="set_param", target="desk.max_weight", change="0.9", rationale="r"), 1)
    with pytest.raises(InvalidLever):
        apply(st, Recommendation(lever="set_param", target="cost_bps", change="1", rationale="r"), 1)
    c2 = apply(st, Recommendation(lever="set_param", target="desk.max_weight", change="25%", rationale="r"), 1)
    assert st.params["desk.max_weight"] == 0.25 and c2["before"] == 0.30 and c2["after"] == 0.25
    c3 = apply(st, Recommendation(lever="set_family_focus", target="idea", change="emphasise trend, volatility; avoid mean reversion", rationale="r"), 1)
    assert st.params["family_focus"] == {"emphasise": ["trend", "volatility"], "avoid": ["mean_reversion"]}
    apply(st, Recommendation(lever="retire_strategy", target="sma_cross", change="", rationale="r"), 1)
    assert st.kept() == []
    with pytest.raises(InvalidLever):
        apply(st, Recommendation(lever="retire_strategy", target="nope", change="", rationale="r"), 1)
    r = apply(st, Recommendation(lever="revert", target="change 2", change="", rationale="too wide"), season=2)
    assert st.params["desk.max_weight"] == 0.30 and r["lever"] == "revert"
    assert st.changelog()[1]["status"] == "reverted" and st.changelog()[1]["reverted_by"] == r["id"]
    with pytest.raises(InvalidLever):
        revert(st, 2, 2)  # already reverted
    rm = apply(st, Recommendation(lever="remove_lesson", target="trader_momentum", change="1", rationale="r"), 2)
    assert st.lessons("trader_momentum") == []
    revert(st, rm["id"], 2)
    assert st.lessons("trader_momentum")[0]["text"].startswith("If RSI14")
    assert parse_focus("Focus on volatility") == {"emphasise": ["volatility"], "avoid": []}
