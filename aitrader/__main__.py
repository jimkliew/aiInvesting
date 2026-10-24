"""Command line: fetch, backtest, campaign, serve, replay, status."""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")  # yfinance emits pandas deprecation noise

from .config import Universe, load_universe
from .events import EventBus, read_trace


def _universe(args) -> Universe:
    u = Universe.quick() if getattr(args, "quick", False) else load_universe(getattr(args, "universe", "universe.yaml"))
    if getattr(args, "quick", False):
        u.start = "2019-01-01"
    if getattr(args, "seasons", None):
        u.seasons = args.seasons
    return u


def _llm(args, bus):
    if getattr(args, "no_llm", False):
        return None
    from .llm import LLM

    llm = LLM(model=args.model, bus=bus)
    ok, msg = llm.health()
    print(msg)
    if not ok:
        sys.exit(1)
    return llm


def _print_event(ev):
    text = ev.payload.get("text")
    if text:
        who = ev.agent or ev.kind
        print(f"[{ev.ts[11:19]}] S{ev.season or '-'} {who:>16}: {text}")


def cmd_status(args):
    from .llm import LLM

    ok, msg = LLM(model=args.model).health()
    print(msg)
    sys.exit(0 if ok else 1)


def cmd_fetch(args):
    from .agents.data_agent import run_data_agent

    bus = EventBus()
    bus.subscribe(_print_event)
    u = _universe(args)
    llm = _llm(args, bus)
    res = run_data_agent(llm, u, bus, args.data_dir, use_llm=llm is not None)
    print("\n" + res.report)
    print(f"\nTickers: {', '.join(res.tickers)} + {u.benchmark}. Manifest sha256 {res.manifest['sha256'][:12]}")


def cmd_backtest(args):
    from .backtest import BASELINES, metrics, run
    from .data import compute_features, fetch_prices

    u = _universe(args)
    prices = fetch_prices(u.all_tickers, start=u.start, cache_dir=Path(args.data_dir) / "raw")
    feats = compute_features(prices)
    print(f"{'strategy':<20}{'return':>10}{'cagr':>8}{'sharpe':>8}{'max dd':>9}{'turnover':>10}")
    for name, fn in BASELINES.items():
        m = metrics(run(fn(prices, feats).fillna(0.0), prices, u.cost_bps))
        print(f"{name:<20}{m.total_return * 100:>9.1f}%{m.cagr * 100:>7.1f}%{m.sharpe:>8.2f}{m.max_dd * 100:>8.1f}%{m.turnover * 100:>9.0f}%")


def cmd_campaign(args):
    from .orchestrator import Controls, Orchestrator
    from .store import RunStore

    u = _universe(args)
    store = RunStore(args.runs, args.resume)
    bus = EventBus(store.path("trace.jsonl"))
    bus.subscribe(_print_event)
    llm = _llm(args, bus)
    personas = [p.strip() for p in args.personas.split(",") if p.strip()]
    orch = Orchestrator(u, store, llm, bus, Controls(), personas=personas, apply_mode=args.apply, quick=args.quick,
                        data_dir=args.data_dir, use_llm_data=not args.no_llm_data)
    t0 = time.time()
    orch.run_campaign(u.seasons)
    print(f"\nDone in {(time.time() - t0) / 60:.1f} min. Run folder: {store.dir}")
    for r in store.track_record():
        print(f"  S{r['season']} {r['label']}: team {r['team'] * 100:+.1f}%  SPY {r['spy'] * 100:+.1f}%  book {r['book_name']}")


def cmd_serve(args):
    import uvicorn

    from .web.server import create_app

    app = create_app(runs_dir=args.runs, data_dir=args.data_dir, model=args.model)
    print(f"Mission Control at http://localhost:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def cmd_replay(args):
    events = read_trace(Path(args.run) / "trace.jsonl")
    delay = 0 if args.speed <= 0 else 1.0 / args.speed
    for ev in events:
        _print_event(ev)
        if delay:
            time.sleep(delay)
    print(f"{len(events)} events")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aitrader", description="An AI investment team you can run on your laptop with Ollama.")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--universe", default="universe.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="check Ollama and the model"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("fetch", help="run the Data Agent"); s.add_argument("--quick", action="store_true"); s.add_argument("--no-llm", action="store_true"); s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("backtest", help="baseline strategies over the full history"); s.add_argument("--quick", action="store_true"); s.set_defaults(fn=cmd_backtest)
    s = sub.add_parser("campaign", help="run seasons with the full team")
    s.add_argument("--seasons", type=int); s.add_argument("--personas", default="momentum")
    s.add_argument("--quick", action="store_true", help="3 tickers, 1 idea, 4 weeks, 2 seasons")
    s.add_argument("--apply", choices=["auto", "approve"], default="auto"); s.add_argument("--resume", help="campaign id to continue")
    s.add_argument("--no-llm-data", action="store_true", help="deterministic data step, no Data Agent")
    s.set_defaults(fn=cmd_campaign)
    s = sub.add_parser("serve", help="start Mission Control"); s.add_argument("--port", type=int, default=8000); s.add_argument("--host", default="127.0.0.1"); s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("replay", help="print a recorded run"); s.add_argument("run"); s.add_argument("--speed", type=float, default=5); s.set_defaults(fn=cmd_replay)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
