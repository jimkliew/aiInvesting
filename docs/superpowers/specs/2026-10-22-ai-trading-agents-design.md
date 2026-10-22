# AI Trading Agents Lab — Design Spec

**Date:** 2026-10-22
**Status:** Draft for review
**Owner:** Jim Liew
**Build window:** 2 days (2026-10-23 → 2026-10-24)

---

## 1. Purpose

A teaching repo that lets students answer one question with their own experiments:

> **How well can an AI agent trade?**

Everything runs locally. The only requirement is [Ollama](https://ollama.com) and
an open-weight model. **No API keys, no paid services, no cloud.**

Students get two agents and a harness that scores them honestly:

| Agent | Job | "Can an AI…" question it answers |
|---|---|---|
| **Data Agent** | Gather, validate and cache market data from a plain-English brief | …assemble a clean dataset without hand-holding? |
| **Strategy Agent** | Propose, code, back-test and iterate on trading rules | …do quant research? |
| **Trader Agent** *(mode of the same harness)* | Make periodic BUY/SELL/HOLD decisions from a point-in-time snapshot | …trade discretionarily? |

Both agents are benchmarked against dumb baselines (buy-and-hold, SMA crossover)
on an **out-of-sample test window the agents never see** until the end.

The repo is as much about **agent engineering best practices** as about trading.
Every practice is named in the code and README so students can point to it.

## 2. What was said vs. what is assumed

**Stated by Jim**

- Students must be able to run it with nothing but Ollama. Free, open-source models.
- One agent gathers data; after that, an agent back-tests strategies.
- Use agent best practices.
- See what can be built in the next 2 days.

**Assumptions (correct me)**

| # | Assumption | Why |
|---|---|---|
| A1 | US equities + ETFs, **daily bars**, via `yfinance` (no key). | Free, reliable, familiar to finance students. Crypto via public exchange endpoints is a stretch goal. |
| A2 | Default universe: ~12 liquid names + SPY benchmark, 2015-01-01 → today. | Small enough to run on a laptop in minutes; large enough to be interesting. |
| A3 | **Long-only**, target weight per asset in [0, 1], daily or weekly rebalance, flat cost in basis points. No shorting, leverage or margin in v1. | Keeps the engine ~150 lines and readable. Shorting is a student exercise. |
| A4 | Default model **`qwen3:8b`** (already on this machine). `--model` flag to swap. | Supports tool calling + JSON-schema output (verified today). Fits 16 GB laptops. |
| A5 | Python 3.11+ managed with **`uv`**, CLI first, optional notebook tour. | `uv run` gives students one-command setup. |
| A6 | Students are finance-literate, mixed coding skill. | Favors readable code over clever code. |
| A7 | Private machines; strategy code written by the LLM is still sandboxed. | It is a best practice worth teaching even if the risk is low. |

## 3. Environment verified today (2026-10-22)

| Check | Result |
|---|---|
| Ollama | 0.40.4 running; `qwen3:8b` pulled |
| Tool calling with qwen3:8b | Works; correct tool + arguments on first try (4.5 s incl. load) |
| JSON-schema structured output | Works; valid `{action, confidence, reason}` in 1.9 s |
| `uv pip install yfinance pandas numpy ollama pyarrow matplotlib` | Installs clean (uv picked Python 3.12) |
| `yfinance` SPY download | 41 rows for Jan–Feb 2024 in 0.6 s, no key |
| Hardware | Mac Studio M4 Max, 36 GB |

Implication: ~2 s per structured decision → a weekly-rebalance trader simulation
over a 2-year test window (~100 decisions) runs in **under 5 minutes** per ticker.

## 4. Approaches considered for the agent layer

**A. Hand-rolled minimal runtime on the `ollama` Python client — RECOMMENDED**
~200 lines: tool registry via decorator, bounded tool-calling loop, structured
output via JSON schema, pydantic validation, JSONL trace per run.
*Pros:* students see the whole loop; zero framework churn; works fully offline.
*Cons:* we write it ourselves (small).

**B. PydanticAI with the Ollama provider**
*Pros:* typed outputs, built-in retries, tool decorators, good docs.
*Cons:* one more abstraction between the student and the model; version churn.
Offered as a **student exercise**: "port the Strategy Agent to PydanticAI".

**C. LangGraph + langchain-ollama**
*Pros:* name recognition, graph state, checkpointing.
*Cons:* heavy, verbose, API changes often, and an 8B model's failures are harder
to debug through it. Not chosen.

**Backtester:** a small in-repo vectorized engine instead of `vectorbt`/`backtrader`.
Transparent, testable with a hand-computed example, and the LLM-written
strategies plug into one stable 1-function interface.

## 5. Agent best practices this repo demonstrates

Each is named in code comments and in `README.md` → "Practices".

| # | Practice | Where it lives |
|---|---|---|
| P1 | **LLM reasons, tools compute.** The model never does arithmetic or touches raw DataFrames. | `aitrader/tools/*` |
| P2 | **Small, typed, documented tools** (≤ 6 per agent) returning compact text/JSON. | `@tool` decorator in `agent.py` |
| P3 | **Structured outputs enforced by schema**, validated by pydantic, retried with the error fed back. | `llm.py: structured()` |
| P4 | **Bounded loops**: max steps, wall-clock budget, max tool calls per run. | `agent.py: run()` |
| P5 | **Observability**: every run gets a `run_id`; prompts, tool calls, outputs go to `runs/<id>/trace.jsonl`. | `trace.py` |
| P6 | **Guardrail — no lookahead.** Data is sliced *as-of* a date before the model sees it; engine lags execution by one bar; a perturbation test proves a strategy didn't peek. | `backtest/lookahead.py` |
| P7 | **Guardrail — sandboxed code.** LLM-written strategy code runs with an AST allowlist, restricted builtins, time limit. | `backtest/sandbox.py` |
| P8 | **Evaluation-first.** Fixed train / validation / test split. Agents see train+val only; test is scored once at the end. Number of strategies tried is reported (multiple-testing honesty). | `backtest/splits.py`, `report/` |
| P9 | **Reproducibility.** Temperature 0 for decisions, pinned model tag, dataset hash in the manifest, prompts stored with results. | `data/manifest.json`, `runs/` |
| P10 | **Memory.** Strategy Agent keeps a *lab notebook* of hypotheses + results so it doesn't repeat itself. | `runs/<id>/notebook.jsonl` |
| P11 | **Human-in-the-loop.** Agents propose and explain; reports show rationale; students grade. | `report/` |
| P12 | **Small-model ergonomics.** Short system prompts, one decision per call, worked examples, `think=False` by default. | prompts in `aitrader/prompts/` |
| P13 | **Graceful degradation.** `--no-llm` runs the deterministic path so the course works even if a laptop can't run the model well. | CLI flags |

## 6. Architecture

```
aiInvesting/
├── pyproject.toml              # uv project; deps: ollama pandas numpy yfinance pyarrow pydantic rich matplotlib
├── README.md                   # 5-minute quickstart + "Practices" + exercises
├── universe.yaml               # default tickers, dates, costs, split dates
├── aitrader/
│   ├── cli.py                  # python -m aitrader {fetch|backtest|research|trade-sim|report}
│   ├── llm.py                  # Ollama wrapper: chat(), structured(schema), health check, retries
│   ├── agent.py                # Agent base: @tool registry, bounded tool loop, trace hook
│   ├── trace.py                # run_id, JSONL trace writer
│   ├── prompts/                # one .md per agent system prompt (students edit these)
│   ├── data/
│   │   ├── fetch.py            # yfinance → data/raw/<TICKER>.parquet, cache, retry/backoff
│   │   ├── quality.py          # gaps, NaNs, zero volume, min history, split sanity → QualityReport
│   │   ├── features.py         # returns, SMA/EMA, RSI, realized vol, drawdown, 12-1 momentum
│   │   ├── manifest.py         # dataset hash + metadata
│   │   └── agent.py            # DataAgent (brief → plan → fetch → check → fix → summarize)
│   ├── backtest/
│   │   ├── engine.py           # weights(t) → positions(t+1) → PnL with costs → equity curve
│   │   ├── metrics.py          # CAGR, vol, Sharpe, Sortino, max DD, Calmar, turnover, hit rate
│   │   ├── splits.py           # train / val / test windows
│   │   ├── strategies/         # baselines: buy_hold, sma_cross, momentum_12_1, rsi_mean_reversion
│   │   ├── sandbox.py          # safe exec of LLM-written generate_signals()
│   │   ├── lookahead.py        # perturbation test for peeking
│   │   ├── strategy_agent.py   # research loop (propose → code → test → critique → iterate)
│   │   └── trader_agent.py     # periodic discretionary decisions from as-of snapshots
│   └── report/
│       ├── leaderboard.py      # metrics table across strategies × splits
│       └── render.py           # markdown report + equity-curve PNGs
├── data/                       # generated; git-ignored except manifest.json
├── runs/                       # generated; one folder per agent run
├── tests/                      # pytest; LLM mocked; one opt-in live test
└── notebooks/01_tour.ipynb     # optional guided walkthrough
```

### 6.1 Data Agent

**Input:** a brief, e.g. `"12 large-cap US tech names plus SPY, 2015 to today"`, or
`universe.yaml` directly with `--no-llm`.

**Tools (deterministic):** `propose_tickers(sector, n)` (from a bundled list, no web),
`fetch_prices(tickers, start, end)`, `check_quality(tickers)`,
`replace_ticker(bad, reason)`, `write_manifest(notes)`.

**Loop:** plan → fetch → read quality report → fix problems (drop/replace tickers
with short history or gaps) → write a short human-readable `data/REPORT.md`
explaining what was gathered and why. Max 12 tool calls.

**Why an LLM here at all?** Fetching is deterministic. The agent's job is the
*judgment* around it: turning a vague brief into a universe, triaging the quality
report, explaining the dataset. This is the first lesson: **don't use an LLM
where a function will do.** The `--no-llm` path makes the point concrete.

**Outputs:** `data/raw/*.parquet`, `data/features/*.parquet`, `data/manifest.json`
(tickers, dates, row counts, SHA-256 of the combined prices), `data/REPORT.md`.

### 6.2 Backtest engine

One interface every strategy — baseline or LLM-written — implements:

```python
def generate_signals(prices: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Return target weights in [0, 1] indexed like prices (date × ticker).
    May only use information available at or before each row's date."""
```

Engine: clip weights to [0, 1], normalise if the sum exceeds 1, **shift by one
bar** (decide at close *t*, hold from *t+1*), apply cost = `bps × |Δweight|`,
compound daily returns, produce equity curve and per-period returns.
Metrics computed per split. A 5-bar hand-worked example is the unit test.

### 6.3 Strategy Agent (research loop)

```
for i in 1..N (default 8):
    notebook   = read_lab_notebook()              # P10
    hypothesis = llm.structured(HypothesisSchema)  # idea + why + which features
    code       = llm.structured(CodeSchema)        # generate_signals body
    ok, err    = sandbox.check_and_compile(code)   # P7
    if not ok: critique = err; continue
    peek       = lookahead.test(code)              # P6
    if peek:   critique = "strategy uses future data"; continue
    train_m    = backtest(code, split="train")
    val_m      = backtest(code, split="val")
    notebook.append(hypothesis, code, train_m, val_m, critique=None)
    critique   = llm.structured(CritiqueSchema)    # overfit? too much turnover? next idea?
best = argmax(val_sharpe)   # chosen on validation only
report(best on TEST, plus baselines on TEST, plus "strategies tried: N")   # P8
```

The agent never sees test-window metrics. The report states how many strategies
were tried so students can discuss selection bias.

### 6.4 Trader Agent (discretionary mode)

For each rebalance date in the chosen window (weekly by default):

1. Build an **as-of snapshot**: last 20 closes, SMA20/50/200 position, RSI14,
   1/3/12-month returns, realized vol, current weight. Text only, ~300 tokens.
2. Ask for `{action: BUY|SELL|HOLD, target_weight, confidence, reason}` with
   temperature 0.
3. Engine executes at the next bar; the rationale is logged to the trace.

Same metrics, same test window, same leaderboard as the rule strategies. Students
can read the transcript and judge whether the reasoning was sound or post-hoc.

### 6.5 Report

`python -m aitrader report` renders `runs/<id>/REPORT.md`:
leaderboard (strategy × split × metrics), equity curves PNG, best strategy's
code and hypothesis, trader rationale excerpts, strategies-tried count, model
tag, dataset hash, wall-clock and token totals.

## 7. Error handling

| Failure | Behaviour |
|---|---|
| Ollama not running / model missing | Health check at start; print the exact `ollama serve` / `ollama pull qwen3:8b` command and exit 1. |
| `yfinance` rate limit / network | 3 retries with backoff; serve from parquet cache if present; quality report flags stale data. |
| Invalid JSON / schema from model | Up to 3 retries with the validation error appended to the prompt; then raise `AgentError` and record in trace. |
| LLM strategy code raises or times out | Caught in sandbox; traceback becomes the critique for the next iteration. |
| Lookahead detected | Iteration rejected, reason fed back; counted in report. |
| Agent exceeds step/time budget | Loop stops, partial results reported, trace marks `budget_exceeded`. |

## 8. Testing

- **Unit (no Ollama):** engine 5-bar known-answer; metrics on synthetic series;
  split boundaries; sandbox rejects `import os`, `open()`, `.shift(-1)`; lookahead
  test catches a deliberately peeking strategy; manifest hash is stable.
- **Agent logic (mocked LLM):** a `FakeLLM` returns canned structured outputs so
  the research loop and trader loop are tested end-to-end in < 5 s.
- **Live (opt-in, `pytest -m ollama`):** one smoke run of each agent with
  `qwen3:8b` on 2 tickers, 1 iteration.
- **Experiment sanity:** buy-and-hold SPY metrics match a hand calculation from
  the raw parquet.

## 9. Two-day build schedule

**Day 1 — foundation (useful even without an LLM)**

| Block | Deliverable |
|---|---|
| AM | Repo scaffold, `pyproject.toml`, CLI skeleton, `data/fetch+quality+features+manifest` with tests |
| PM | `backtest/engine+metrics+splits`, 4 baselines, `leaderboard`, `python -m aitrader backtest` works end-to-end |
| Late | `llm.py` + `agent.py` + `trace.py`; Data Agent wired; README quickstart |

**Day 2 — agents and the experiment**

| Block | Deliverable |
|---|---|
| AM | `sandbox.py`, `lookahead.py`, Strategy Agent loop with lab notebook; mocked-LLM tests |
| PM | Trader Agent weekly sim; `report/render.py`; run the full default experiment; write findings into README |
| Late | Student exercises section; `--no-llm` path verified; tag `v0.1` |

**Stretch (only if ahead):** walk-forward validation, crypto via public exchange
endpoints, model comparison (`qwen3:4b` vs `8b` vs `14b`), notebook tour.

## 10. Student experience

```bash
ollama pull qwen3:8b
git clone <repo> && cd aiInvesting
uv run python -m aitrader fetch     "12 large-cap US tech names plus SPY, 2015 to today"
uv run python -m aitrader backtest                   # baselines leaderboard
uv run python -m aitrader research  --iterations 8   # Strategy Agent
uv run python -m aitrader trade-sim --ticker SPY     # Trader Agent
uv run python -m aitrader report
```

Hardware guidance in README:

| Laptop RAM | Model | Notes |
|---|---|---|
| 8 GB | `qwen3:4b` | Slower, more JSON retries |
| 16 GB | `qwen3:8b` (default) | Verified |
| 32 GB+ | `qwen3:14b` | Better code, ~2× slower |

**Exercises:** add shorting; add a news tool from an RSS feed; swap to PydanticAI;
tighten the sandbox; compare two models; detect overfitting from the notebook.

## 11. Out of scope for v1

Live trading, broker APIs, intraday data, options, portfolio optimisation, any
service that needs an API key, any paid model.

## 12. Open decisions for Jim

1. **Agent layer:** hand-rolled on the `ollama` client (recommended) vs PydanticAI.
2. **Scope:** daily US equities, long-only — OK for v1?
3. **Both evaluation modes** (Strategy Agent + Trader Agent) in 2 days, or Strategy Agent only with Trader as stretch?
4. **Default model:** `qwen3:8b` — OK?
5. **Hosting:** where should students clone from (GitHub org/repo name)?
