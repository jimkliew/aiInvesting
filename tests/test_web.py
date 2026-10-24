import json

import pytest
from fastapi.testclient import TestClient

from aitrader.web.server import create_app
from tests.test_orchestrator import _run, default_responses
from tests.fakes import FakeLLM


@pytest.fixture
def app_client(tmp_path, synthetic):
    store, _ = _run(tmp_path, FakeLLM(default=default_responses()))
    app = create_app(runs_dir=str(tmp_path / "runs"), data_dir=str(tmp_path / "data"), model="fake")
    with TestClient(app) as c:
        yield c, store


def test_index_and_state(app_client):
    c, store = app_client
    r = c.get("/")
    assert r.status_code == 200 and "Mission Control" in r.text
    st = c.get("/api/state").json()
    assert st["campaign"]["id"] == store.id and st["campaign"]["running"] is False
    assert [s["state"] for s in st["seasons"]] == ["done", "done"]
    assert len(st["progress"]["daily"]) > 50 and st["progress"]["scorecard"]["seasons_done"] == 2
    assert st["this_season"]["n"] == 2 and st["this_season"]["figures"]["team"] is not None
    assert any(c_["lever"] == "set_param" for c_ in st["progress"]["changes"])


def test_lists_and_prompts(app_client):
    c, store = app_client
    assert len(c.get("/api/notebook").json()) >= 2
    assert len(c.get("/api/desk").json()) > 0
    assert len(c.get("/api/reviews").json()) == 2
    assert c.get("/api/changelog").json()[0]["lever"] == "set_param"
    agents = [p["agent"] for p in c.get("/api/prompts").json()]
    assert "trader_momentum" in agents and "review" in agents
    before = c.get("/api/prompts/critic").json()["prompt"]
    try:
        r = c.put("/api/prompts/critic", json={"prompt": before + "\n# edited\n"})
        assert r.status_code == 200
        assert c.get("/api/changelog").json()[-1]["lever"] == "manual_edit"
    finally:
        c.put("/api/prompts/critic", json={"prompt": before})


def test_strategy_and_runs(app_client, tmp_path, synthetic):
    c, store = app_client
    # cache prices so the strategy endpoint can read them
    (tmp_path / "data" / "raw").mkdir(parents=True, exist_ok=True)
    for t in synthetic.columns:
        synthetic[t].to_frame("close").to_parquet(tmp_path / "data" / "raw" / f"{t}.parquet")
    s = c.get("/api/strategy", params={"season": 1, "ticker": "AAPL"}).json()
    assert s["book"]["name"].startswith("sma_cross") and s["series"] and "weight" in s["series"][-1]
    runs = c.get("/api/runs").json()
    assert runs[0]["id"] == store.id and runs[0]["seasons_done"] == [1, 2]
    assert c.post(f"/api/runs/{store.id}/open").json()["ok"]


def test_replay_matches_trace(app_client):
    c, store = app_client
    n_lines = sum(1 for _ in open(store.path("trace.jsonl")))
    with c.stream("GET", f"/api/runs/{store.id}/replay", params={"speed": 0}) as r:
        body = "".join(r.iter_text())
    assert body.count("\ndata: {") + body.count("data: {\"") >= n_lines
    assert "event: end" in body


def test_status_without_campaign(tmp_path):
    app = create_app(runs_dir=str(tmp_path / "none"), data_dir=str(tmp_path / "data"), model="nope:0b")
    with TestClient(app) as c:
        s = c.get("/api/status").json()
        assert s["campaign"] is None and s["running"] is False
        assert c.get("/api/state").json()["campaign"] is None
        assert c.post("/api/control/pause").status_code == 400
