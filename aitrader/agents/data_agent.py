"""Data Agent: the only agent that uses tool calling. Fetching is code; the judgment is the agent.

If the model misbehaves or Ollama is unavailable, the deterministic path still
produces the dataset (practice P13: graceful degradation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .. import prompts
from ..agent import tool
from ..config import Universe
from ..data import check_quality, compute_features, fetch_prices, write_manifest
from ..data.quality import clean
from ..llm import AgentError

CANDIDATES = ["ADBE", "INTC", "CSCO", "QCOM", "TXN", "IBM", "NOW", "INTU", "AMAT", "MU", "PYPL", "UBER"]


@dataclass
class DataResult:
    prices: pd.DataFrame
    features: dict[str, pd.DataFrame]
    manifest: dict
    report: str
    tickers: list[str]
    used_llm: bool = False
    tool_calls: list[str] = field(default_factory=list)


def _deterministic(universe: Universe, data_dir: Path, on_ticker=None) -> tuple[pd.DataFrame, object]:
    prices = fetch_prices(universe.all_tickers, start=universe.start, cache_dir=data_dir / "raw", on_ticker=on_ticker)
    span_years = (prices.index.max() - prices.index.min()).days / 365.25 if len(prices) else 0.0
    # a ticker is "short" when it misses more than a fifth of the dataset's span, capped at 8 years
    rep = check_quality(prices, min_years=min(8.0, 0.8 * span_years))
    return prices, rep


def run_data_agent(llm, universe: Universe, bus=None, data_dir: str | Path = "data", use_llm: bool = True,
                   brief: str | None = None) -> DataResult:
    data_dir = Path(data_dir)
    state: dict = {"prices": None, "report": None, "tickers": list(universe.tickers), "calls": []}

    def emit(kind, **p):
        if bus:
            bus.emit(kind, **p)

    def on_ticker(t, n, how):
        emit("data_fetch", text=f"{t}: {n} days ({how})", ticker=t, rows=n, how=how)

    def do_fetch(tickers: list[str], allow_candidates: bool = False) -> str:
        tickers = [t.strip().upper() for t in tickers if t and t.strip()]
        allowed = set(universe.tickers) | {universe.benchmark} | (set(CANDIDATES) if allow_candidates else set())
        bad = [t for t in tickers if t not in allowed]
        if bad:
            return (f"error: {bad} are not in the brief; nothing fetched. Fetch the brief's tickers first and use "
                    f"replace_ticker only for a name the quality check flags as short")
        state["tickers"] = [t for t in tickers if t != universe.benchmark]
        u = Universe(tickers=state["tickers"], benchmark=universe.benchmark, start=universe.start)
        prices, rep = _deterministic(u, data_dir, on_ticker)
        state["prices"], state["quality"] = prices, rep
        return f"fetched {len(prices.columns)} tickers, {len(prices)} trading days, {prices.index.min().date()} to {prices.index.max().date()}"

    @tool("Download daily adjusted closes for these tickers (SPY is added automatically)")
    def fetch_prices_tool(tickers: list[str]) -> str:
        state["calls"].append("fetch_prices")
        return do_fetch(tickers)

    @tool("Report trading days, history length and internal gaps for the fetched data")
    def check_quality_tool() -> str:
        state["calls"].append("check_quality")
        if state["prices"] is None:
            return "error: nothing fetched yet; call fetch_prices first"
        return state["quality"].summary()

    @tool("Replace one ticker with another from the candidate list and refetch")
    def replace_ticker_tool(bad: str, replacement: str) -> str:
        state["calls"].append("replace_ticker")
        bad, replacement = bad.strip().upper(), replacement.strip().upper()
        if replacement not in CANDIDATES:
            return f"error: {replacement} is not in the candidate list {CANDIDATES}"
        if bad not in state["tickers"]:
            return f"error: {bad} is not in the current universe {state['tickers']}"
        q = state.get("quality")
        if q is None:
            return "error: run check_quality first; replacements are only allowed for tickers it flags as short"
        if bad not in q.short:
            return (f"refused: {bad} has full history ({q.first_dates.get(bad, '?')} to {q.last_date}); "
                    f"only tickers flagged as short may be replaced. Short: {q.short or 'none'}")
        new = [replacement if t == bad else t for t in state["tickers"]]
        return do_fetch(new, allow_candidates=True)

    @tool("Save the plain-English report about the dataset")
    def write_report_tool(text: str) -> str:
        state["calls"].append("write_report")
        state["report"] = text.strip()
        return "report saved"

    tools = {"fetch_prices": fetch_prices_tool, "check_quality": check_quality_tool,
             "replace_ticker": replace_ticker_tool, "write_report": write_report_tool}
    used_llm = False
    if use_llm and llm is not None:
        brief = brief or (f"Universe: {', '.join(universe.tickers)}. Benchmark: {universe.benchmark}. "
                          f"Daily data from {universe.start} to today. Candidate replacements: {', '.join(CANDIDATES)}.")
        try:
            final = llm.chat_with_tools(prompts.load("data"), brief, tools, max_steps=8, agent="data")
            used_llm = True
            if state["report"] is None and final:
                state["report"] = final.strip()
        except AgentError as e:
            emit("agent_error", agent="data", error=str(e), text=f"Data Agent failed ({e}); using the deterministic path")
        except Exception as e:  # Ollama down, etc.
            emit("agent_error", agent="data", error=str(e), text=f"Data Agent unavailable ({type(e).__name__}); using the deterministic path")
    if state["prices"] is None:
        prices, rep = _deterministic(Universe(tickers=state["tickers"], benchmark=universe.benchmark, start=universe.start),
                                     data_dir, on_ticker)
        state["prices"], state["quality"] = prices, rep
        if state["report"] is None:
            state["report"] = rep.summary()
    prices = clean(state["prices"])
    manifest = write_manifest(prices, data_dir / "manifest.json", notes=state["report"] or "")
    (data_dir / "REPORT.md").write_text(f"# Dataset report\n\n{state['report']}\n\nManifest sha256: {manifest['sha256']}\n")
    features = compute_features(prices)
    emit("data_ready", text=f"Dataset ready: {len(prices.columns)} tickers, {len(prices)} days, hash {manifest['sha256'][:8]}",
         tickers=list(prices.columns), rows=len(prices), sha256=manifest["sha256"], report=state["report"])
    return DataResult(prices=prices, features=features, manifest=manifest, report=state["report"] or "",
                      tickers=[t for t in prices.columns if t != universe.benchmark], used_llm=used_llm, tool_calls=state["calls"])
