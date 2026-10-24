import pandas as pd
import pytest

from aitrader.seasons import calendar, rebalance_dates, trim_to_data
from aitrader.store import RunStore


def test_calendar_windows():
    cal = calendar("2025-01-01", 6)
    s1 = cal[0]
    assert (str(s1.start.date()), str(s1.end.date())) == ("2025-01-01", "2025-03-31")
    assert tuple(str(d.date()) for d in s1.validation) == ("2024-01-01", "2024-12-31")
    assert tuple(str(d.date()) for d in s1.train) == ("2015-01-01", "2023-12-31")
    assert s1.label == "2025 Q1" and s1.visible_end == s1.validation[1]
    assert str(cal[5].end.date()) == "2026-06-30" and cal[5].label == "2026 Q2"


def test_trim_to_data_marks_partial():
    s = calendar("2025-01-01", 1)[0]
    t = trim_to_data(s, "2025-02-14")
    assert t.partial and str(t.end.date()) == "2025-02-14"
    assert not trim_to_data(s, "2025-12-31").partial


def test_rebalance_dates_weekly_and_monthly():
    idx = pd.bdate_range("2025-01-01", "2025-03-31")
    w = rebalance_dates(idx, "2025-01-01", "2025-03-31", "weekly")
    assert 12 <= len(w) <= 14 and all(d.weekday() <= 1 for d in w[1:])  # first week may start mid-week
    m = rebalance_dates(idx, "2025-01-01", "2025-03-31", "monthly")
    assert [d.month for d in m] == [1, 2, 3]


def test_store_round_trips(tmp_runs):
    st = RunStore(tmp_runs, "c1")
    st.save_meta(model="qwen3:8b")
    assert st.meta()["model"] == "qwen3:8b"
    st.notebook_add({"name": "a", "family": "trend", "status": "kept", "season": 1, "val": {"sharpe": 1.2}})
    st.notebook_add({"name": "b", "family": "trend", "status": "discarded", "season": 1})
    st.notebook_add({"name": "a", "family": "trend", "status": "kept", "season": 2, "val": {"sharpe": 0.9}})
    kept = st.kept()
    assert [e["name"] for e in kept] == ["a"] and kept[0]["season"] == 2
    st.retire("a")
    assert st.kept() == []
    st.reinstate("a")
    assert len(st.kept()) == 1
    assert "val Sharpe 0.9" in st.notebook_summary()
    lid = st.add_lesson("trader_momentum", "no dip buying", season=1)
    assert st.lesson_texts("trader_momentum") == [f"{lid}. (after S1) no dip buying"]
    assert st.remove_lesson("trader_momentum", lid) and st.lessons("trader_momentum") == []
    c = st.changelog_append({"lever": "set_param", "target": "desk.max_weight", "change": "0.3"})
    assert c["id"] == 1 and st.changelog()[0]["status"] == "active"
    st.update_change(1, status="reverted", reverted_by=2)
    assert st.changelog()[0]["reverted_by"] == 2
    st.append_track_record({"season": 1, "team": 0.01})
    st.append_track_record({"season": 1, "team": 0.02})
    assert st.track_record() == [{"season": 1, "team": 0.02}]
    st.params.validate_set("desk.max_weight", 0.2)
    st.save_params()
    assert RunStore(tmp_runs, "c1").params["desk.max_weight"] == 0.2
    st.set_quant_book(1, "a", "def generate_signals(prices, features): ...", 1.2)
    assert st.quant_book(1)["name"] == "a"
    st.save_scorecard(1, {"team": {"total_return": 0.01}})
    assert st.seasons_done() == [1]
    assert RunStore.list_campaigns(tmp_runs)[0]["id"] == "c1"
