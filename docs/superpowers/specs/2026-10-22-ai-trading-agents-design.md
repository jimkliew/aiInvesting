# AI Trading Agents Lab — Design Spec

**Date:** 2026-10-22 (rev 2: agent roster, swarm rules, web UI)
**Status:** Draft for review
**Owner:** Jim Liew
**Build window:** 2 days (2026-10-23 → 2026-10-24)

---

## 1. Purpose

A teaching repo that lets students answer one question with their own experiments:

> **How well can an AI agent trade?**

Everything runs locally. The only requirement is [Ollama](https://ollama.com) and
an open-weight model. **No API keys, no paid services, no cloud.**

Students get a small, fixed **swarm of specialised agents**, a deterministic
harness that scores them honestly, and a **local web page ("Mission Control")**
for running and watching it all live during the online course.

The agents are benchmarked against dumb baselines (buy-and-hold, SMA crossover)
on an **out-of-sample test window the agents never see** until the end.

The repo is as much about **agent engineering best practices** as about trading.
Every practice is named in the code and README so students can point to it.

## 2. What was said vs. what is assumed

**Stated by Jim**

- Students must be able to run it with nothing but Ollama. Free, open-source models.
- One agent gathers data; after that, agents back-test strategies.
- Use agent best practices.
- A swarm of agents, but kept under control.
- A web page to run through everything during the online course.
- See what can be built in the next 2 days.

**Assumptions (correct me)**

| # | Assumption | Why |
|---|---|---|
| A1 | US equities + ETFs, **daily bars**, via `yfinance` (no key). | Free, reliable, familiar to finance students. Crypto via public exchange endpoints is a stretch goal. |
| A2 | Default universe: ~12 liquid names + SPY benchmark, 2015-01-01 → today. | Small enough to run on a laptop in minutes; large enough to be interesting. |
| A3 | **Long-only**, target weight per asset in [0, 1], daily or weekly rebalance, flat cost in basis points. No shorting, leverage or margin in v1. | Keeps the engine ~150 lines and readable. Shorting is a student exercise. |
| A4 | Default model **`qwen3:8b`** (already on this machine). `--model` flag to swap. | Supports tool calling + JSON-schema output (verified today). Fits 16 GB laptops. |
| A5 | Python 3.11+ managed with **`uv`**, CLI + local web UI, optional notebook tour. | `uv run` gives students one-command setup. |
| A6 | Students are finance-literate, mixed coding skill. | Favors readable code over clever code. |
| A7 | Private machines; strategy code written by the LLM is still sandboxed. | It is a best practice worth teaching even if the risk is low. |
| A8 | The web page runs on `localhost`; Jim screen-shares it in class; students run their own copy later. | No hosting, no auth, nothing to pay for. |

## 3. Environment verified today (2026-10-22)

| Check | Result |
|---|---|
| Ollama | 0.40.4 running; `qwen3:8b` pulled |
| Tool calling with qwen3:8b | Works; correct tool + arguments on first try (4.5 s incl. load) |
| JSON-schema structured output | Works; valid `{action, confidence, reason}` in 1.9 s |
| `uv pip install yfinance pandas numpy ollama pyarrow matplotlib` | Installs clean (uv picked Python 3.12) |
| `yfinance` SPY download | 41 rows for Jan–Feb 2024 in 0.6 s, no key |
| Hardware | Mac Studio M4 Max, 36 GB |

Implication: ~2–5 s per LLM call. Budget math is in §6.6.

## 4. Approaches considered for the agent layer

**A. Hand-rolled minimal runtime on the `ollama` Python client — RECOMMENDED**
"Hand-rolled" means we write the agent loop ourselves (~200 lines): send goal +
tool schemas → if the model calls a tool, run it and return the result → repeat
until a final answer or the step budget runs out. Plus a `@tool` decorator, a
`structured(schema)` helper with retries, and a JSONL trace writer.
*Pros:* students see the whole loop; zero framework churn; works fully offline.
*Cons:* we write it ourselves (small).

**B. PydanticAI with the Ollama provider**
*Pros:* typed outputs, built-in retries, tool decorators, good docs.
*Cons:* one more abstraction between the student and the model; version churn.
Offered as a **student exercise**: "port the Coder Agent to PydanticAI".

**C. LangGraph + langchain-ollama**
*Pros:* name recognition, graph state, checkpointing.
*Cons:* heavy, verbose, API changes often, and an 8B model's failures are harder
to debug through it. Not chosen.

**Backtester:** a small in-repo vectorized engine instead of `vectorbt`/`backtrader`.
Transparent, testable with a hand-computed example, and the LLM-written
strategies plug into one stable 1-function interface.

**Web UI:** FastAPI + one static HTML page with Server-Sent Events (recommended)
vs Streamlit. See §6.7 for the comparison.

## 5. Agent best practices this repo demonstrates

Each is named in code comments and in `README.md` → "Practices".

| # | Practice | Where it lives |
|---|---|---|
| P1 | **LLM reasons, tools compute.** The model never does arithmetic or touches raw DataFrames. | `aitrader/tools/*` |
| P2 | **Small, typed, documented tools** (≤ 4 per agent) returning compact text/JSON. | `@tool` decorator in `agent.py` |
| P3 | **Structured outputs enforced by schema**, validated by pydantic, retried with the error fed back. | `llm.py: structured()` |
| P4 | **Bounded loops**: max steps, wall-clock budget, max tool calls per run, global LLM-call budget. | `agent.py`, `orchestrator.py` |
| P5 | **Observability**: every run gets a `run_id`; prompts, tool calls, outputs go to `runs/<id>/trace.jsonl` and stream to the UI. | `events.py` |
| P6 | **Guardrail — no lookahead.** Data is sliced *as-of* a date before the model sees it; engine lags execution by one bar; a perturbation test proves a strategy didn't peek. | `backtest/lookahead.py` |
| P7 | **Guardrail — sandboxed code.** LLM-written strategy code runs with an AST allowlist, restricted builtins, time limit. | `backtest/sandbox.py` |
| P8 | **Evaluation-first.** Fixed train / validation / test split. Agents see train+val only; test is scored once at the end ("Reveal test" button). Number of strategies tried is reported. | `backtest/splits.py`, `report/` |
| P9 | **Reproducibility.** Temperature 0 for decisions, pinned model tag, dataset hash in the manifest, prompts stored with results, every run replayable. | `data/manifest.json`, `runs/` |
| P10 | **Memory.** The research swarm shares a *lab notebook* of hypotheses + results so it doesn't repeat itself. | `runs/<id>/notebook.jsonl` |
| P11 | **Human-in-the-loop.** Agents propose and explain; the UI has Step mode; students grade. | `web/` |
| P12 | **Small-model ergonomics.** Short system prompts, one decision per call, worked examples, `think=False` by default, info-in-prompt over tool-fetching for the research agents. | `aitrader/prompts/` |
| P13 | **Graceful degradation.** `--no-llm` runs the deterministic path; Replay mode shows a recorded run when live is too slow. | CLI flags, `web/` |
| P14 | **Workflows over free-form agents.** The orchestrator is code, not an LLM. Agents do judgment inside fixed phases. | `orchestrator.py` |
| P15 | **Typed hand-offs, not chat.** Agents never talk to each other; they read/write pydantic artifacts on a shared run store. | `store.py`, `schemas.py` |

## 6. Architecture

```
aiInvesting/
├── pyproject.toml              # uv; deps: ollama pandas numpy yfinance pyarrow pydantic rich matplotlib fastapi uvicorn
├── README.md                   # 5-minute quickstart + "Practices" + exercises
├── universe.yaml               # default tickers, dates, costs, split dates
├── aitrader/
│   ├── cli.py                  # python -m aitrader {fetch|backtest|research|trade-sim|report|run-all|serve}
│   ├── llm.py                  # Ollama wrapper: chat(), structured(schema), health check, retries
│   ├── agent.py                # Agent base: @tool registry, bounded tool loop, event hook
│   ├── orchestrator.py         # deterministic state machine: phases, budgets, step/pause/stop
│   ├── store.py                # run store (blackboard): artifacts, notebook, leaderboard; JSON files per run
│   ├── schemas.py              # pydantic models every agent reads/writes (Hypothesis, StrategyCode, Review, Decision, …)
│   ├── events.py               # Event dataclass, JSONL trace writer, in-process pub/sub for the UI
│   ├── prompts/                # one .md per agent (data, idea, coder, critic, trader_*, pm, reporter)
│   ├── data/                   # fetch.py quality.py features.py manifest.py agent.py
│   ├── backtest/               # engine.py metrics.py splits.py strategies/ sandbox.py lookahead.py
│   ├── agents/                 # data_agent.py idea_agent.py coder_agent.py critic_agent.py trader_agent.py pm_agent.py reporter_agent.py
│   ├── report/                 # leaderboard.py render.py (markdown + PNG)
│   └── web/
│       ├── server.py           # FastAPI app: REST + SSE
│       └── static/             # index.html app.js style.css + vendored chart lib (offline)
├── data/                       # generated; git-ignored except manifest.json
├── runs/                       # generated; one folder per run (trace, artifacts, report)
├── tests/                      # pytest; LLM mocked; one opt-in live test
└── notebooks/01_tour.ipynb     # optional guided walkthrough
```

### 6.1 Data Agent (phase 1)

**Input:** a brief, e.g. `"12 large-cap US tech names plus SPY, 2015 to today"`, or
`universe.yaml` directly with `--no-llm`.

**Tools (deterministic):** `propose_tickers(sector, n)` (from a bundled list, no web),
`fetch_prices(tickers, start, end)`, `check_quality(tickers)`,
`replace_ticker(bad, reason)`.

**Loop:** plan → fetch → read quality report → fix problems (drop/replace tickers
with short history or gaps) → write a short human-readable `data/REPORT.md`.
Max 12 tool calls.

**Why an LLM here at all?** Fetching is deterministic. The agent's job is the
*judgment* around it: turning a vague brief into a universe, triaging the quality
report, explaining the dataset. First lesson: **don't use an LLM where a
function will do.** The `--no-llm` path makes the point concrete.

**Outputs:** `data/raw/*.parquet`, `data/features/*.parquet`, `data/manifest.json`
(tickers, dates, row counts, SHA-256 of combined prices), `data/REPORT.md`.

### 6.2 Backtest engine (deterministic)

One interface every strategy — baseline or LLM-written — implements:

```python
def generate_signals(prices: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Return target weights in [0, 1] indexed like prices (date × ticker).
    May only use information available at or before each row's date."""
```

Engine: clip weights to [0, 1], normalise if the sum exceeds 1, **shift by one
bar** (decide at close *t*, hold from *t+1*), apply cost = `bps × |Δweight|`,
compound daily returns, produce equity curve and per-period returns.
Metrics per split: CAGR, vol, Sharpe, Sortino, max drawdown, Calmar, turnover,
hit rate. A 5-bar hand-worked example is the unit test.

### 6.3 Research swarm (phase 2)

Three LLM roles share one lab notebook; the loop itself is code.

| Agent | Reads | Writes (schema) | LLM calls |
|---|---|---|---|
| **Idea Agent** | feature catalog, lab notebook (what was tried, what scored) | `Hypothesis[]` — K distinct ideas across families: trend, mean-reversion, volatility, cross-sectional momentum | 1 per round |
| **Coder Agent** | one `Hypothesis` (+ sandbox / lookahead / runtime error on retry) | `StrategyCode` — body of `generate_signals` | 1–3 per hypothesis |
| **Critic Agent** | code + train/val metrics + notebook | `Review` — verdict KEEP/DISCARD, concerns (overfit, turnover, concentration), suggestion for next round | 1 per hypothesis |

```
round r in 1..R (default 2), K ideas per round (default 4)  → ≤ 8 strategies
    ideas = IdeaAgent(notebook)
    for h in ideas:
        code = CoderAgent(h)
        for attempt in 1..3:
            ok, err = sandbox.compile_and_check(code)        # P7
            if ok and lookahead.passes(code): break           # P6
            code = CoderAgent(h, feedback=err)
        else: notebook.add(h, status="failed", err); continue
        m_train, m_val = backtest(code, "train"), backtest(code, "val")
        review = CriticAgent(code, m_train, m_val, notebook)
        notebook.add(h, code, m_train, m_val, review)
best = argmax over KEEP strategies of val_sharpe                    # chosen on validation only
scorer.evaluate_on_test(best, baselines)                           # revealed once, P8
```

No agent sees test-window numbers. The report states how many strategies were
tried (selection-bias honesty). These agents use **no tools**: everything they
need is put in the prompt (feature catalog ≈ 40 lines, notebook ≈ 1 line per
strategy). For an 8B model this is more reliable and cheaper than tool fetching.

### 6.4 Trading desk (phase 3)

**Trader Agents** make discretionary decisions on the test window at a weekly
cadence from a point-in-time snapshot (last 20 closes, SMA20/50/200 position,
RSI14, 1/3/12-month returns, realized vol, current weight; ~300 tokens).
Output: `Decision {action: BUY|SELL|HOLD, target_weight, confidence, reason}`,
temperature 0. Engine executes next bar; rationale logged.

Three **personas** share the code and differ only by prompt file:
`trader_momentum.md`, `trader_contrarian.md`, `trader_risk_averse.md`.
Default runs one persona; `--personas 3` runs all three as competing strategies
on the leaderboard (the swarm demo for class).

**PM Agent (optional, `--committee`):** each week reads the three `Decision`s
and emits one `Allocation`. Demonstrates the committee pattern; costs one extra
call per week. Stretch priority.

### 6.5 Reporter Agent (phase 4)

Reads the leaderboard, notebook, and transcript excerpts; writes the narrative
section of `runs/<id>/REPORT.md`. Students compare its prose to the numbers
(hallucination check as an exercise). 1–2 calls.

### 6.6 Orchestrator and swarm rules — how this stays in hand

The swarm is **logical specialisation, not a free-for-all**. Rules enforced in code:

1. **Fixed roster.** Seven roles (Data, Idea, Coder, Critic, Trader×3 personas, PM, Reporter). Agents cannot spawn agents.
2. **Orchestrator is code.** A Python state machine runs phases in a fixed order. No LLM decides "who talks next."
3. **No agent-to-agent chat.** Agents read and write typed pydantic artifacts on the run store. No conversation loops.
4. **One prompt file, one output schema, ≤ 4 tools, ≤ 3 retries** per agent.
5. **Global budgets** (`max_llm_calls`, `max_minutes`, `max_strategies`) enforced by the orchestrator and shown as a meter in the UI. Hitting a budget stops cleanly with partial results.
6. **Sequential by default.** On one laptop Ollama serves one model; concurrency buys nothing. `--parallel 2` exists to make that point.
7. **Everything is replayable** from `trace.jsonl`.

Default-run budget on M4 Max with `qwen3:8b` (2–5 s per call):

| Phase | Calls | Time |
|---|---|---|
| Data | ≤ 12 | ~1 min |
| Research (2 rounds × 4 ideas) | ~40 | ~4 min |
| Trading desk (1 persona, 1-year test, weekly) | ~52 | ~3 min |
| Reporter | 2 | ~10 s |
| **Default total** | **~105** | **~8 min** |
| Class demo (`--personas 3 --committee`, 2-year test) | ~450 | ~25 min → use Replay |

An 8 GB laptop with `qwen3:4b` is ~2–3× slower. Replay mode covers class time.

### 6.7 Web UI — "Mission Control"

**Purpose:** one page Jim can screen-share to run the whole pipeline live, step
through agent turns, and reveal the test results at the end. Students run the
same page locally afterwards.

**Stack (recommended):** FastAPI + uvicorn backend; one static `index.html` with
vanilla JS and CSS; **Server-Sent Events** stream the agent trace live; a small
MIT chart library vendored into `static/` so the page works offline. No npm, no
build step, no CDN. Start with `uv run python -m aitrader serve` → `http://localhost:8000`.

*Why not Streamlit:* its rerun model fights long-running background jobs and
live token-by-token streaming; it also pulls in a heavy dependency. SSE + one
HTML file is ~400 lines and fully ours.

**Layout**

```
┌──────────────────────────────────────────────────────────────────────────┐
│ AI Trading Lab   ● Ollama qwen3:8b   ● Data 13 tickers 2015–2026  run #7 │
│ Budget: LLM calls 23/105 · 04:12 elapsed · [Step] [Pause] [Stop]         │
├──────────────┬──────────────────────────────┬────────────────────────────┤
│ PIPELINE     │ LIVE AGENT FEED              │ LEADERBOARD                │
│ ① Data   ✔   │ Idea Agent  → 4 hypotheses   │ strategy    train val test │
│ ② Research ▶ │ Coder Agent → code (41 ln)   │ buy&hold    0.61 0.55  ██  │
│   rounds 2   │ Sandbox ✔  Lookahead ✔       │ sma_cross   0.48 0.30  ██  │
│   ideas  4   │ Backtest train 0.92 val 0.71 │ h3_momo_vol 0.92 0.71  ██  │
│ ③ Trade sim  │ Critic: KEEP (turnover high) │ …                          │
│   personas 1 │ Idea Agent (round 2)…        │ [Reveal test ▸]            │
│ ④ Report     │                              │ equity curves ▁▂▃▅▆        │
├──────────────┴──────────────────────────────┴────────────────────────────┤
│ [Notebook] [Trading desk] [Prompts] [Report] [Runs ▸ replay 1×/5×/∞]     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Classroom features**

| Feature | Why it matters in class |
|---|---|
| **Run / Step / Pause / Stop** per phase | Step mode advances one agent turn at a time so Jim can narrate. |
| **Live feed** colour-coded by agent, tool calls collapsible, structured outputs pretty-printed | Students watch the agents "think". |
| **Reveal test** button | Test column is masked until clicked. Teaches hold-out discipline with a moment of drama. |
| **Prompts tab** (view, edit, save, re-run) | Students change a persona's prompt and see the leaderboard move. |
| **Replay** of any previous run at 1× / 5× / instant | Class demo works even if live Ollama is slow. Ship the repo with one recorded run. |
| **Budget meter** | Makes "bounded loops" visible. |
| **Runs tab** | Compare two runs side by side (stretch). |

**API**

```
GET  /                      static page
GET  /api/status            ollama + dataset + current run + budget
POST /api/run/{phase}       body: params; starts phase in a background thread
POST /api/control/{step|pause|resume|stop}
GET  /api/events            SSE stream of Event{ts, run_id, phase, agent, kind, payload}
GET  /api/leaderboard?reveal=false
GET  /api/runs              list; GET /api/runs/{id}/replay?speed=5
GET  /api/prompts/{agent}   PUT to save
```

The orchestrator publishes `Event`s to an in-process queue **and** to
`trace.jsonl`; the SSE endpoint and Replay both read the same event shape, so
the UI code has one path.

## 7. Error handling

| Failure | Behaviour |
|---|---|
| Ollama not running / model missing | Health check at start (CLI and UI banner); print the exact `ollama serve` / `ollama pull qwen3:8b` command. |
| `yfinance` rate limit / network | 3 retries with backoff; serve from parquet cache if present; quality report flags stale data. |
| Invalid JSON / schema from model | Up to 3 retries with the validation error appended; then `AgentError`, recorded in trace, phase continues with next item. |
| LLM strategy code raises or times out | Caught in sandbox; traceback becomes Coder feedback (≤ 3 attempts), then marked failed in notebook. |
| Lookahead detected | Attempt rejected, reason fed back; counted in report. |
| Budget exceeded | Orchestrator stops the phase cleanly, partial results kept, trace marks `budget_exceeded`, UI shows it. |
| Browser disconnects from SSE | Client auto-reconnects and replays missed events from the trace offset. |

## 8. Testing

- **Unit (no Ollama):** engine 5-bar known-answer; metrics on synthetic series;
  split boundaries; sandbox rejects `import os`, `open()`, `.shift(-1)`; lookahead
  test catches a deliberately peeking strategy; manifest hash is stable;
  orchestrator budget stops at the limit.
- **Agent logic (mocked LLM):** a `FakeLLM` returns canned structured outputs so
  the research loop, trading desk and reporter run end-to-end in < 5 s.
- **Web:** FastAPI `TestClient` — status, start a mocked run, receive SSE events,
  leaderboard masks test until reveal, replay returns the same events as live.
- **Live (opt-in, `pytest -m ollama`):** one smoke run with `qwen3:8b` on 2
  tickers, 1 round, 1 idea.
- **Experiment sanity:** buy-and-hold SPY metrics match a hand calculation from
  the raw parquet.

## 9. Two-day build schedule with priorities

P0 = must ship, P1 = should, P2 = stretch.

**Day 1 — foundation**

| Block | Deliverable | Pri |
|---|---|---|
| AM | Repo scaffold, `pyproject`, CLI skeleton, `schemas.py`, `events.py` + `store.py` (designed for the UI from the start), `data/` fetch + quality + features + manifest, tests | P0 |
| PM | `backtest/` engine + metrics + splits + 4 baselines + leaderboard; `python -m aitrader backtest` end-to-end | P0 |
| Late | `llm.py`, `agent.py`, `orchestrator.py` skeleton with budgets; Data Agent wired; README quickstart | P0 |

**Day 2 — swarm and Mission Control**

| Block | Deliverable | Pri |
|---|---|---|
| AM | `sandbox.py`, `lookahead.py`; Idea / Coder / Critic agents + notebook; one Trader persona; mocked-LLM tests | P0 |
| AM | Two more personas; Reporter Agent | P1 |
| PM | `web/server.py` + `index.html`: status bar, pipeline cards, live feed, leaderboard with Reveal, Replay | P0 |
| PM | Prompts tab, equity chart, Step mode | P1 |
| Late | Run the full default experiment; record a replay; write findings + exercises in README; tag `v0.1` | P0 |
| — | PM committee, compare-runs, walk-forward, crypto, model comparison, notebook tour | P2 |

**Main risk:** the UI squeezes Day 2. Mitigations: event bus built on Day 1 so the
UI is a thin consumer; single HTML file; Replay guarantees a working class demo.

## 10. Student experience

```bash
ollama pull qwen3:8b
git clone <repo> && cd aiInvesting
uv run python -m aitrader serve          # open http://localhost:8000 and click Run
# or the CLI equivalents:
uv run python -m aitrader fetch "12 large-cap US tech names plus SPY, 2015 to today"
uv run python -m aitrader backtest
uv run python -m aitrader research --rounds 2 --ideas 4
uv run python -m aitrader trade-sim --personas 1
uv run python -m aitrader report
```

| Laptop RAM | Model | Notes |
|---|---|---|
| 8 GB | `qwen3:4b` | Slower, more JSON retries; use Replay in class |
| 16 GB | `qwen3:8b` (default) | Verified |
| 32 GB+ | `qwen3:14b` | Better code, ~2× slower |

**Exercises:** edit a trader persona prompt and re-run; add shorting; add an RSS
news tool; port the Coder Agent to PydanticAI; tighten the sandbox; compare two
models; find overfitting in the notebook; fact-check the Reporter.

## 11. Out of scope for v1

Live trading, broker APIs, intraday data, options, portfolio optimisation,
hosted deployment, authentication, any service that needs an API key, any paid
model, dynamic agent spawning.

## 12. Open decisions for Jim

1. **Agent layer:** hand-rolled on the `ollama` client (recommended) vs PydanticAI.
2. **Scope:** daily US equities, long-only, ~12 tickers + SPY — OK for v1?
3. **Roster:** Data, Idea, Coder, Critic, 3 Trader personas, PM (stretch), Reporter — OK? Anything to cut?
4. **Web UI stack:** FastAPI + single HTML page with SSE (recommended) vs Streamlit.
5. **Default model:** `qwen3:8b` — OK?
6. **Hosting:** GitHub org/repo name students will clone from.
