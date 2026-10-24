"""Mission Control server: REST for state, Server-Sent Events for the live feed and replay."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .. import prompts
from ..backtest.strategies import tradeable
from ..config import Universe, load_universe
from ..data.manifest import read_manifest
from ..events import Event, EventBus, read_trace
from ..seasons import calendar
from ..store import RunStore

STATIC = Path(__file__).parent / "static"


class CampaignRequest(BaseModel):
    seasons: int | None = None
    personas: list[str] = ["momentum"]
    quick: bool = False
    apply_mode: str = "auto"
    model: str | None = None
    use_llm_data: bool = True


class PromptBody(BaseModel):
    prompt: str


class AppState:
    def __init__(self, runs_dir: str, data_dir: str, model: str):
        self.runs_dir = Path(runs_dir)
        self.data_dir = Path(data_dir)
        self.model = model
        self.store: RunStore | None = None
        self.orch = None
        self.bus: EventBus | None = None
        self.thread: threading.Thread | None = None
        self.controls = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue] = set()
        self.error: str | None = None
        self.universe = Universe()
        # open the most recent campaign for display
        runs = RunStore.list_campaigns(self.runs_dir)
        if runs:
            self.store = RunStore(self.runs_dir, runs[-1]["id"])

    @property
    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def _fanout(self, ev: Event) -> None:
        if not self.loop:
            return
        data = ev.to_json()
        for q in list(self.queues):
            self.loop.call_soon_threadsafe(q.put_nowait, data)

    def start_campaign(self, req: CampaignRequest) -> str:
        from ..llm import LLM
        from ..orchestrator import Controls, Orchestrator

        if self.running:
            raise HTTPException(409, "a campaign is already running")
        u = Universe.quick() if req.quick else load_universe("universe.yaml")
        if req.quick:
            u.start = "2019-01-01"
        if req.seasons:
            u.seasons = req.seasons
        self.universe = u
        store = RunStore(self.runs_dir)
        bus = EventBus(store.path("trace.jsonl"))
        bus.subscribe(self._fanout)
        model = req.model or self.model
        llm = LLM(model=model, bus=bus)
        ok, msg = llm.health()
        if not ok:
            raise HTTPException(503, msg)
        controls = Controls()
        orch = Orchestrator(u, store, llm, bus, controls, personas=req.personas or ["momentum"], apply_mode=req.apply_mode,
                            quick=req.quick, data_dir=self.data_dir, use_llm_data=req.use_llm_data)
        self.store, self.bus, self.orch, self.controls, self.error = store, bus, orch, controls, None

        def run():
            try:
                orch.run_campaign(u.seasons)
            except Exception as e:  # already emitted as campaign_error
                self.error = str(e)

        self.thread = threading.Thread(target=run, daemon=True, name="orchestrator")
        self.thread.start()
        return store.id


def _prices_cached(data_dir: Path, tickers: list[str]) -> pd.DataFrame | None:
    frames = {}
    for t in tickers:
        p = data_dir / "raw" / f"{t}.parquet"
        if p.exists():
            frames[t] = pd.read_parquet(p)["close"]
    if not frames:
        return None
    df = pd.DataFrame(frames).sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def build_state(st: AppState) -> dict[str, Any]:
    store = st.store
    out: dict[str, Any] = {"campaign": None, "seasons": [], "this_season": None, "progress": None, "params": None}
    if store is None:
        return out
    meta = store.meta()
    uni = meta.get("universe") or st.universe.to_dict()
    n_seasons = meta.get("seasons") or uni.get("seasons") or 6
    orch = st.orch
    cur_season = orch.current_season.n if (orch and orch.current_season and st.running) else None
    budget = orch.budget.to_dict() if orch else None
    out["campaign"] = {
        "id": store.id, "running": st.running, "model": meta.get("model"), "personas": meta.get("personas"),
        "apply_mode": meta.get("apply_mode"), "quick": meta.get("quick"), "seasons": n_seasons, "season": cur_season,
        "phase": orch.current_phase if (orch and st.running) else None,
        "agent": st.bus.agent if (st.bus and st.running) else None, "budget": budget, "error": st.error,
        "universe": uni, "created": meta.get("created"),
    }
    out["params"] = dict(store.params)
    tr = {r["season"]: r for r in store.track_record()}
    done = store.seasons_done()
    cal = calendar(uni.get("campaign_start", "2025-01-01"), n_seasons, uni.get("start", "2015-01-01"))
    seasons = []
    for s in cal:
        row = tr.get(s.n)
        state = "done" if s.n in done else ("live" if s.n == cur_season else "queued")
        seasons.append({"n": s.n, "label": s.label, "start": str(s.start.date()), "end": str(s.end.date()), "state": state,
                        **({k: row.get(k) for k in ("team", "spy", "book", "desk", "partial", "book_name")} if row else {})})
    out["seasons"] = seasons

    # progress: chain daily equity across scored seasons
    daily_rows, chain = [], {"team": 1.0, "book": 1.0, "desk": 1.0, "spy": 1.0}
    pnl_team: list[float] = []
    for n in done:
        sc = store.scorecard(n) or {}
        prev = None
        for d in sc.get("daily", []):
            row = {"date": d["date"], "season": n}
            for k in chain:
                row[k] = round(chain[k] * d.get(k, 1.0), 6)
            if prev is not None:
                pnl_team.append(row["team"] / prev - 1)
            prev = row["team"]
            daily_rows.append(row)
        if sc.get("daily"):
            last = sc["daily"][-1]
            for k in chain:
                chain[k] *= last.get(k, 1.0)
    changes = [{"id": c["id"], "season": c.get("season"), "lever": c["lever"], "target": c.get("target"), "change": str(c.get("change", ""))[:160],
                "status": c.get("status"), "applies_from_season": (c.get("season") or 0) + 1} for c in store.changelog()]
    import math
    sharpe = 0.0
    if len(pnl_team) > 2:
        s = pd.Series(pnl_team)
        sharpe = float(s.mean() / s.std() * math.sqrt(252)) if s.std() > 0 else 0.0
    eq = pd.Series([r["team"] for r in daily_rows]) if daily_rows else pd.Series([1.0])
    max_dd = float((eq / eq.cummax() - 1).min()) if len(eq) else 0.0
    nb = store.notebook()
    lessons = sum(len(v) for v in store.all_lessons().values())
    rows_done = [tr[n] for n in done if n in tr]
    out["progress"] = {
        "daily": daily_rows, "changes": changes,
        "scorecard": {
            "seasons_done": len(rows_done),
            "seasons_beating_spy": sum(1 for r in rows_done if (r.get("team") or 0) > (r.get("spy") or 0)),
            "excess_pts": round(((chain["team"] - 1) - (chain["spy"] - 1)) * 100, 2) if rows_done else None,
            "cum_team": round(chain["team"] - 1, 4), "cum_spy": round(chain["spy"] - 1, 4),
            "cum_book": round(chain["book"] - 1, 4), "cum_desk": round(chain["desk"] - 1, 4),
            "sharpe_oos": round(sharpe, 2), "max_dd": round(max_dd, 4),
            "strategies_tried": len(nb), "kept": len([e for e in nb if e.get("status") == "kept"]),
            "lessons": lessons, "reverted": len([c for c in store.changelog() if c.get("status") == "reverted"]),
            "llm_calls": sum(r.get("llm_calls", 0) or 0 for r in rows_done),
        },
        "table": [{**r, "changes_applied": [c["id"] for c in store.changelog() if c.get("season") == r["season"]]} for r in rows_done],
    }

    # this season: the live one, else the last scored
    n = cur_season or (done[-1] if done else None)
    if n:
        sc = store.scorecard(n)
        book = store.quant_book(n) or {}
        decisions = store.decisions(n)
        weeks_done = len({d["week"] for d in decisions})
        kept = store.kept()
        leaderboard = []
        for e in kept:
            leaderboard.append({"name": e["name"], "kind": "candidate", "val_sharpe": (e.get("val") or {}).get("sharpe"),
                                "season_return": sc["book"]["total_return"] if sc and e["name"] == book.get("name") else None,
                                "is_book": e["name"] == book.get("name")})
        if sc:
            leaderboard.append({"name": "Desk, " + ", ".join(meta.get("personas") or ["momentum"]), "kind": "desk", "val_sharpe": None,
                                "season_return": sc["desk"]["total_return"]})
            for bname, m in (sc.get("baselines") or {}).items():
                if "total_return" in m:
                    leaderboard.append({"name": bname, "kind": "baseline", "val_sharpe": None, "season_return": m["total_return"]})
        label = next((s["label"] for s in seasons if s["n"] == n), f"Season {n}")
        out["this_season"] = {
            "n": n, "label": label, "scored": sc is not None, "partial": sc.get("partial") if sc else False,
            "book": book, "weeks_done": weeks_done, "weeks_total": len({}),
            "figures": {k: sc[k]["total_return"] for k in ("team", "spy", "book", "desk")} if sc else None,
            "daily": sc.get("daily") if sc else None, "leaderboard": leaderboard,
            "decisions_count": len(decisions),
        }
    return out


def create_app(runs_dir: str = "runs", data_dir: str = "data", model: str = "qwen3:8b") -> FastAPI:
    st = AppState(runs_dir, data_dir, model)
    app = FastAPI(title="aitrader Mission Control")

    @app.on_event("startup")
    async def _startup():
        st.loop = asyncio.get_running_loop()

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        ok, msg = False, "not checked"
        try:
            from ..llm import LLM
            ok, msg = LLM(model=st.model).health()
        except Exception as e:
            msg = str(e)
        orch = st.orch
        return {
            "ollama": {"ok": ok, "message": msg}, "model": st.model, "data": read_manifest(st.data_dir / "manifest.json"),
            "campaign": st.store.id if st.store else None, "running": st.running,
            "season": orch.current_season.n if (orch and orch.current_season and st.running) else None,
            "phase": orch.current_phase if (orch and st.running) else None,
            "agent": st.bus.agent if (st.bus and st.running) else None,
            "budget": orch.budget.to_dict() if orch else None,
            "paused": bool(st.controls and st.controls.paused), "error": st.error,
            "runs": [r["id"] for r in RunStore.list_campaigns(st.runs_dir)],
        }

    @app.post("/api/campaign")
    def start(req: CampaignRequest):
        cid = st.start_campaign(req)
        return {"campaign": cid}

    @app.post("/api/control/{action}")
    def control(action: str):
        if not st.controls:
            raise HTTPException(400, "no campaign")
        fn = {"pause": st.controls.pause, "resume": st.controls.resume, "step": st.controls.step, "stop": st.controls.stop}.get(action)
        if not fn:
            raise HTTPException(404, action)
        fn()
        return {"ok": True, "paused": st.controls.paused, "stopped": st.controls.stopped}

    async def _sse(gen):
        return StreamingResponse(gen, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/events")
    async def events(request: Request, since: int = 0):
        q: asyncio.Queue = asyncio.Queue()
        st.queues.add(q)

        async def gen():
            try:
                if st.store:
                    for ev in read_trace(st.store.path("trace.jsonl")):
                        if ev.seq > since:
                            yield f"id: {ev.seq}\ndata: {ev.to_json()}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=15)
                        yield f"data: {data}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                st.queues.discard(q)

        return await _sse(gen())

    @app.get("/api/state")
    def state():
        return JSONResponse(build_state(st))

    @app.get("/api/notebook")
    def notebook():
        if not st.store:
            return []
        ret = st.store.retired()
        return [{**{k: v for k, v in e.items() if k != "code"}, "retired": e["name"] in ret, "code": e.get("code", "")} for e in st.store.notebook()]

    @app.get("/api/desk")
    def desk():
        return st.store.decisions() if st.store else []

    @app.get("/api/reviews")
    def reviews():
        return st.store.reviews() if st.store else []

    @app.get("/api/changelog")
    def changelog():
        return st.store.changelog() if st.store else []

    @app.get("/api/pending")
    def pending():
        return st.store.pending() if st.store else []

    @app.post("/api/pending/{idx}/{decision}")
    def decide_pending(idx: int, decision: str):
        from .. import levers
        from ..schemas import Recommendation

        items = st.store.pending()
        if idx < 0 or idx >= len(items):
            raise HTTPException(404, "no such recommendation")
        item = items[idx]
        if decision == "accept":
            try:
                rec = Recommendation(**{k: item[k] for k in Recommendation.model_fields if k in item})
                change = levers.apply(st.store, rec, season=item.get("season", 0), source="human")
                item["status"] = "applied"
                item["change_id"] = change["id"]
                if st.bus:
                    st.bus.emit("change_applied", text=f"You accepted: {change['lever']} {change['target']} -> {str(change['change'])[:120]}",
                                **{k: v for k, v in change.items() if k != "detail"})
            except levers.InvalidLever as e:
                raise HTTPException(400, str(e))
        else:
            item["status"] = "rejected"
            if st.bus:
                st.bus.emit("recommendation_rejected", text=f"You rejected: {item['lever']} {item.get('target')}", **item)
        st.store.save_pending(items)
        return items

    @app.get("/api/prompts")
    def prompt_list():
        lessons = st.store.all_lessons() if st.store else {}
        return [{"agent": a, "words": len(prompts.raw(a).split()), "lessons": len(lessons.get(a, []))} for a in prompts.list_agents()]

    @app.get("/api/prompts/{agent}")
    def prompt_get(agent: str):
        try:
            text = prompts.raw(agent)
        except FileNotFoundError:
            raise HTTPException(404, agent)
        return {"agent": agent, "prompt": text, "lessons": st.store.lessons(agent) if st.store else []}

    @app.put("/api/prompts/{agent}")
    def prompt_put(agent: str, body: PromptBody):
        if agent not in prompts.list_agents():
            raise HTTPException(404, agent)
        prompts.save(agent, body.prompt)
        if st.store:
            season = st.orch.current_season.n if (st.orch and st.orch.current_season) else 0
            st.store.changelog_append({"season": season, "lever": "manual_edit", "target": agent, "change": "prompt edited by hand",
                                       "rationale": "", "source": "human"})
            if st.bus:
                st.bus.emit("change_applied", text=f"Prompt for {agent} edited by hand", lever="manual_edit", target=agent)
        return {"ok": True}

    @app.get("/api/strategy")
    def strategy(season: int | None = None, ticker: str | None = None):
        if not st.store:
            raise HTTPException(404, "no campaign")
        done = st.store.seasons_done()
        n = season or (st.orch.current_season.n if (st.orch and st.orch.current_season) else (done[-1] if done else None))
        if not n:
            raise HTTPException(404, "no season yet")
        book = st.store.quant_book(n) or {}
        w = st.store.weights(n, "book_weights")
        meta = st.store.meta()
        uni = meta.get("universe") or {}
        tickers = uni.get("tickers") or []
        prices = _prices_cached(st.data_dir, list(tickers) + [uni.get("benchmark", "SPY")])
        if prices is None or w is None:
            return {"season": n, "book": book, "tickers": tickers, "series": None}
        t = ticker or (tickers[0] if tickers else None)
        if t not in prices.columns:
            raise HTTPException(404, f"no prices for {t}")
        s = next(x for x in calendar(uni.get("campaign_start", "2025-01-01"), meta.get("seasons") or 6, uni.get("start", "2015-01-01")) if x.n == n)
        start = s.validation[0]
        px = prices[t].loc[start:s.end]
        sma20 = prices[t].rolling(20).mean().loc[start:s.end]
        sma50 = prices[t].rolling(50).mean().loc[start:s.end]
        high20 = prices[t].rolling(20).max().shift(1).loc[start:s.end]
        wt = w[t].reindex(px.index).fillna(0.0) if t in w.columns else pd.Series(0.0, index=px.index)
        ret = px.pct_change().fillna(0)
        held = wt.shift(1).fillna(0)
        eq = (1 + held * ret).cumprod()
        maxw = float(wt.max()) if float(wt.max()) > 0 else 0.3
        hold = (1 + maxw * ret).cumprod()
        series = [{"date": str(d.date()), "close": float(px[d]) if pd.notna(px[d]) else None,
                   "sma20": float(sma20[d]) if pd.notna(sma20[d]) else None, "sma50": float(sma50[d]) if pd.notna(sma50[d]) else None,
                   "high20": float(high20[d]) if pd.notna(high20[d]) else None, "weight": round(float(wt[d]), 4),
                   "equity": round(float(eq[d]), 6), "hold": round(float(hold[d]), 6)} for d in px.index]
        return {"season": n, "label": s.label, "season_start": str(s.start.date()), "book": book, "tickers": tickers, "ticker": t,
                "max_weight": round(maxw, 4), "series": series}

    @app.get("/api/runs")
    def runs():
        return RunStore.list_campaigns(st.runs_dir)

    @app.post("/api/runs/{run_id}/open")
    def open_run(run_id: str):
        if st.running:
            raise HTTPException(409, "stop the running campaign first")
        if not (st.runs_dir / run_id / "campaign.json").exists():
            raise HTTPException(404, run_id)
        st.store = RunStore(st.runs_dir, run_id)
        st.orch = None
        st.bus = None
        return {"ok": True, "campaign": run_id}

    @app.get("/api/runs/{run_id}/replay")
    async def replay(request: Request, run_id: str, speed: float = 5.0):
        p = st.runs_dir / run_id / "trace.jsonl"
        if not p.exists():
            raise HTTPException(404, run_id)
        events_ = read_trace(p)
        delay = 0.0 if speed <= 0 else 1.0 / speed

        async def gen():
            for ev in events_:
                if await request.is_disconnected():
                    break
                yield f"id: {ev.seq}\ndata: {ev.to_json()}\n\n"
                if delay:
                    await asyncio.sleep(delay)
            yield "event: end\ndata: {}\n\n"

        return await _sse(gen())

    return app
