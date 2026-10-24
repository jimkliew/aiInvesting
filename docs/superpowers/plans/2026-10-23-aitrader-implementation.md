# aitrader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Python package `aitrader` described in the spec: data fetch, backtest engine, the seven-agent team on Ollama, rolling-season campaign loop with coach and levers, and the FastAPI server that drives the Mission Control page live.

**Architecture:** A deterministic orchestrator (plain Python state machine) runs phases per season; LLM agents are thin functions over `llm.structured()` with one prompt file and one pydantic schema each. All state lives in a run store on disk (JSON/JSONL/parquet) so the web server, the CLI and replay read the same files. Events flow through an in-process bus to a JSONL trace and to SSE clients.

**Tech Stack:** Python 3.11+, uv, pandas, numpy, yfinance, pyarrow, pydantic v2, ollama (python client), fastapi, uvicorn, pytest. Front end is the existing single-file mockup adapted to live data (vanilla JS, no build).

**Spec:** `docs/superpowers/specs/2026-10-22-ai-trading-agents-design.md`

## Global Constraints

- No API keys, no paid services, no network beyond yfinance and localhost Ollama.
- Default model `qwen3:8b`; every call `temperature=0`, `think=False`; `--model` overrides.
- Long only; weights in [0, 1]; engine lags one bar; cost 5 bp per unit of |Δweight|.
- Seasons are calendar quarters; default campaign 6 seasons from 2025-01-01; expanding train window from 2015-01-01; validation = 12 months before the season.
- Universe fixed per campaign: AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO AMD CRM ORCL NFLX + SPY benchmark (never held).
- Agents: one prompt file in `aitrader/prompts/`, one output schema, ≤ 4 tools, ≤ 3 retries. The Review Agent may only act through `levers.py`.
- Budgets per season: `max_llm_calls` (default 60), `max_minutes` (default 15), `max_strategies` (default 8). Exceeding stops the phase cleanly.
- Everything appended to `runs/<campaign>/trace.jsonl`; replay reads the same event shape the live page receives.
- `--quick` runs 3 tickers + SPY, 1 idea, 1 persona, 2 seasons, 4 weekly decisions per season, for smoke tests.

## Review Focus

1. Ticker with short history (listed after 2015) → quality report flags it; Data Agent replaces or drops it; engine never sees NaN prices (weights 0 before listing). Test in Task 2.
2. Model returns invalid JSON or a schema violation three times → `AgentError` raised, logged as event `agent_error`, the phase continues with the next item; the season still scores. Test in Task 6 with a FakeLLM.
3. Strategy code raises inside the sandbox or exceeds the time limit → rejected with the traceback text, Coder gets up to 3 attempts, then `status="failed"` in the notebook. Test in Task 7.
4. No KEEP candidates in a season → selector falls back to the previous season's book, or to `buy_hold_spy` in season 1, and emits `selector_fallback`. Test in Task 9.
5. Season window extends past the last available data date (e.g. the current quarter) → season is trimmed to available days and marked `partial=True` in the scorecard. Test in Task 4.

---

### Task 1: Project scaffold, config, schemas, events

**Files:**
- Create: `pyproject.toml`, `aitrader/__init__.py`, `aitrader/__main__.py`, `aitrader/config.py`, `aitrader/schemas.py`, `aitrader/events.py`, `universe.yaml`, `tests/conftest.py`, `tests/test_events.py`

**Interfaces:**
- Produces: `Universe` (tickers, benchmark, start, cost_bps, campaign_start, seasons), `Params` (lever-adjustable dict with ranges), pydantic models `Hypothesis, Hypotheses, StrategyCode, Review, Decision, Recommendation, SeasonReview, Metrics`, `Event` dataclass and `EventBus.emit(kind, **payload)`, `EventBus.subscribe(fn)`, JSONL trace writer.

- [ ] Write `tests/test_events.py`: emit two events, assert the trace file has two JSON lines with `ts, campaign, season, phase, agent, kind, payload`; a subscriber receives both.
- [ ] Run it to see it fail (module missing).
- [ ] Implement `events.py` (`Event` dataclass, `EventBus(trace_path)` with `emit`, `subscribe`, context fields `set_context(campaign, season, phase, agent)`), `schemas.py`, `config.py` (`load_universe(path)`, `Params` with `RANGES = {"desk.max_weight": (0.1, 0.4), "critic.min_val_sharpe": (0.3, 1.0), "research.rounds": (1, 3), "research.ideas_per_round": (1, 6), "desk.rebalance": {"weekly", "monthly"}, "selector.max_turnover": (50, 600)}`), `pyproject.toml` with deps and `[tool.pytest.ini_options]`.
- [ ] Run the test to see it pass; `uv run pytest -q`.
- [ ] Commit `feat: scaffold package with config, schemas and event bus`.

### Task 2: Data fetch, quality, features, manifest

**Files:**
- Create: `aitrader/data/__init__.py`, `aitrader/data/fetch.py`, `aitrader/data/quality.py`, `aitrader/data/features.py`, `aitrader/data/manifest.py`, `tests/test_data.py`

**Interfaces:**
- Produces: `fetch_prices(tickers, start, end=None, cache_dir="data/raw") -> pd.DataFrame` (date × ticker adjusted closes, cached as parquet per ticker, 3 retries with backoff); `check_quality(prices, min_years=8) -> QualityReport(ok: list, short: list, gaps: dict)`; `compute_features(prices) -> dict[str, pd.DataFrame]` with keys `ret_1d, sma20, sma50, sma200, rsi14, vol20, mom_12_1, high20, drawdown`; `feature_catalog() -> str` (one line per feature for prompts); `snapshot(prices, features, ticker, as_of, current_weight, max_weight) -> str` (~300 tokens, only rows ≤ as_of); `write_manifest(prices, path, notes) -> str` (sha256 of the CSV bytes of prices).

- [ ] Tests (synthetic prices, no network): features shapes and known values (sma20 of a constant series equals the constant; rsi14 of a monotone rising series is 100); snapshot contains no date after `as_of`; quality flags a column that starts in 2020 when `min_years=8`; manifest hash is stable across two calls.
- [ ] Run, fail, implement, pass.
- [ ] Add `tests/test_data_live.py` marked `@pytest.mark.network` fetching SPY for 2024-01..2024-03 and asserting > 30 rows (skipped by default via `-m "not network"` in pytest config).
- [ ] Commit `feat: data fetch, quality checks, features, manifest`.

### Task 3: Backtest engine, metrics, baselines

**Files:**
- Create: `aitrader/backtest/__init__.py`, `aitrader/backtest/engine.py`, `aitrader/backtest/metrics.py`, `aitrader/backtest/strategies.py`, `tests/test_engine.py`

**Interfaces:**
- Produces: `run(weights, prices, cost_bps=5) -> Result(equity: Series, pnl: Series, weights: DataFrame, turnover: float)`; `metrics(result) -> Metrics(cagr, vol, sharpe, sortino, max_dd, calmar, turnover, hit_rate, total_return, n_days)`; baselines as `generate_signals(prices, features)` functions in `BASELINES = {"buy_hold_spy": ..., "equal_weight": ..., "sma_cross_50_200": ..., "momentum_12_1": ..., "rsi_meanrev": ...}`; `normalise(weights)` (clip to [0,1], scale rows whose sum > 1 down to 1).

- [ ] Test: 5-bar hand-worked example. Prices A: 100,110,99,99,108.9; weights target 1.0 on bar 1, 0 on bar 3. With one-bar lag and 5 bp: equity = [1, 1, 1.1·(1−0.0005·1)=1.09945, 1.09945·0.9·(1−0.0005·1)=0.98901, 0.98901, 0.98901]. Assert within 1e-6. Test `normalise` scales a row [0.8, 0.8] to [0.5, 0.5] and clips −0.2 to 0.
- [ ] Run, fail, implement, pass. Metrics on synthetic series (constant +1%/day → max_dd 0, hit_rate 1.0).
- [ ] Commit `feat: vectorised backtest engine, metrics and baseline strategies`.

### Task 4: Seasons and the run store

**Files:**
- Create: `aitrader/seasons.py`, `aitrader/store.py`, `tests/test_seasons.py`, `tests/test_store.py`

**Interfaces:**
- Produces: `Season(n, start, end, train, validation)` where windows are `(start, end)` date tuples; `calendar(campaign_start, n_seasons, data_start="2015-01-01") -> list[Season]`; `trim_to_data(season, last_date) -> Season` with `partial` flag; `RunStore(root="runs", campaign_id=None)` with `notebook_add(entry)`, `notebook() -> list[dict]`, `kept()`, `lessons(agent) -> list[str]`, `add_lesson(agent, text) -> int`, `remove_lesson(agent, id)`, `changelog_append(change)`, `changelog()`, `params` (load/save), `set_quant_book(season, name)`, `save_season(n, scorecard, decisions, weights)`, `track_record()`, `append_track_record(row)`, `save_review(n, review)`, `reviews()`, `path(...)`, `list_campaigns(root)`.

- [ ] Tests: `calendar("2025-01-01", 6)` → first season 2025-01-01..2025-03-31, validation 2024-01-01..2024-12-31, train 2015-01-01..2023-12-31; sixth season ends 2026-06-30; `trim_to_data` on a season ending after `last_date` returns `partial=True` and end == last_date. Store round-trips notebook entries, lessons with ids, changelog, track record, params.
- [ ] Run, fail, implement, pass. Commit `feat: season calendar and run store`.

### Task 5: Ollama wrapper and tool loop

**Files:**
- Create: `aitrader/llm.py`, `aitrader/agent.py`, `tests/test_llm.py`, `tests/fakes.py`

**Interfaces:**
- Produces: `LLM(model="qwen3:8b", bus=None, budget=None)` with `health() -> (ok, message)`, `structured(system, user, schema: type[BaseModel], agent="", retries=3) -> BaseModel` (uses `ollama.chat(..., format=schema.model_json_schema(), options={"temperature": 0}, think=False)`, validates with `schema.model_validate_json`, on failure appends `"Your previous answer was invalid: {error}. Answer again with only the JSON."`), `chat_with_tools(system, user, tools: dict[str, callable], max_steps=12, agent="") -> str`, `calls` counter; `Budget(max_llm_calls, max_minutes)` with `spend()` raising `BudgetExceeded`; `AgentError`; `FakeLLM(responses: list[str])` in `tests/fakes.py` implementing the same two methods for tests. `@tool(description)` decorator in `agent.py` producing Ollama tool schemas from type hints.

- [ ] Tests with FakeLLM: `structured` returns the model on first valid JSON; retries once on invalid then succeeds, emitting `llm_retry`; raises `AgentError` after 3 invalid; `Budget` raises on the Nth call; tool loop executes a fake tool call and returns the final text.
- [ ] Run, fail, implement, pass. Commit `feat: Ollama wrapper with structured output, retries, budget and tool loop`.

### Task 6: Research agents (Idea, Coder, Critic) and prompts

**Files:**
- Create: `aitrader/agents/__init__.py`, `aitrader/agents/idea_agent.py`, `aitrader/agents/coder_agent.py`, `aitrader/agents/critic_agent.py`, `aitrader/prompts/idea.md`, `aitrader/prompts/coder.md`, `aitrader/prompts/critic.md`, `aitrader/prompts/__init__.py` (`load(name, **vars)` reads the .md, appends `## Lessons from the coach` when lessons exist), `tests/test_research_agents.py`

**Interfaces:**
- Produces: `propose(llm, k, catalog, notebook_summary, family_focus, lessons) -> list[Hypothesis]`; `write_code(llm, hyp, feedback=None) -> StrategyCode`; `review(llm, code, m_train, m_val, notebook_summary, lessons, max_turnover) -> Review`. Prompt texts are those shown in the deck (`docs/slides`), expanded with the interface signature and one worked example each.

- [ ] Tests with FakeLLM canned JSON: propose returns K hypotheses with distinct names; write_code with feedback includes the feedback in the user message; review parses KEEP/DISCARD. Review Focus 2: three invalid answers → `AgentError`.
- [ ] Run, fail, implement, pass. Commit `feat: idea, coder and critic agents with prompts`.

### Task 7: Sandbox and lookahead guard

**Files:**
- Create: `aitrader/backtest/sandbox.py`, `aitrader/backtest/sandbox_runner.py`, `aitrader/backtest/lookahead.py`, `tests/test_sandbox.py`

**Interfaces:**
- Produces: `check_source(code) -> None | raises Rejected(reason, lineno)` (AST: no Import/ImportFrom, no calls to open/eval/exec/compile/__import__/getattr/setattr/delattr, no dunder attribute access, no `.shift(<negative literal>)`, must define `generate_signals`); `run_strategy(code, prices, features, timeout=20) -> pd.DataFrame` executes in a subprocess (`python -m aitrader.backtest.sandbox_runner`) that receives a temp dir with `prices.parquet`, `features/*.parquet`, `code.py`, writes `weights.parquet`; raises `Rejected` with the traceback text on error or timeout; `lookahead_passes(code, prices, features, cut=60) -> bool` compares weights from full data versus data truncated by `cut` rows on the overlapping index (allclose, 1e-9).

- [ ] Tests: rejects `import os`, `open("x")`, `prices.shift(-1)`, `prices.__class__`; accepts the breakout example; a strategy that raises returns `Rejected` with "ZeroDivisionError" in the message; `while True: pass` times out (timeout=3) with "timed out"; lookahead catches a reversed-rolling trick (`prices[::-1].rolling(5).mean()[::-1]`) and passes `sma_cross_50_200`.
- [ ] Run, fail, implement, pass. Commit `feat: sandbox subprocess and lookahead guard`.

### Task 8: Trader agent, snapshots, Review agent, levers

**Files:**
- Create: `aitrader/agents/trader_agent.py`, `aitrader/agents/review_agent.py`, `aitrader/levers.py`, `aitrader/prompts/trader_momentum.md`, `aitrader/prompts/trader_contrarian.md`, `aitrader/prompts/trader_risk_averse.md`, `aitrader/prompts/review.md`, `tests/test_trader_review.py`, `tests/test_levers.py`

**Interfaces:**
- Produces: `decide(llm, persona, snapshot_text, lessons, max_weight) -> Decision`; `coach(llm, packet: ReviewPacket) -> SeasonReview`; `ReviewPacket(scorecard, track_record, changelog, notebook_summary, best_worst).as_text()`; `LEVERS` dict and `apply(store, rec: Recommendation, season) -> dict change | raises InvalidLever`; `revert(store, change_id)`.

- [ ] Tests: decision clamps `target_weight` to `[0, max_weight]`; `set_param` outside range raises `InvalidLever`; `add_lesson` over 300 chars raises; `revert` restores the previous param value and marks the change `reverted_by`; FakeLLM-driven `coach` returns recommendations parsed into the schema.
- [ ] Run, fail, implement, pass. Commit `feat: trader personas, review agent and lever menu`.

### Task 9: Selector, scorer, orchestrator, CLI

**Files:**
- Create: `aitrader/backtest/selector.py`, `aitrader/backtest/scorer.py`, `aitrader/orchestrator.py`, `aitrader/agents/data_agent.py`, `aitrader/prompts/data.md`, modify `aitrader/__main__.py`, `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `select(notebook_entries, params, previous_book) -> (name, code, fallback: bool)`; `score_season(prices, features, season, book_weights, desk_weights, benchmark) -> Scorecard` (book, desk, team, spy, baselines metrics + weekly cumulative series for the Progress chart, `partial`); `Orchestrator(universe, params, store, llm, bus, controls)` with `run_campaign(n_seasons)`, `run_season(season)`, phases `data → research → select → trade → score → review → apply`; `Controls` with `pause()`, `resume()`, `step()`, `stop()` and `checkpoint()` called between agent turns; CLI: `fetch`, `backtest`, `campaign [--seasons N --personas N --quick --model M --apply auto|approve --resume]`, `serve`, `replay`.

- [ ] Tests with FakeLLM and synthetic prices: a 2-season `--quick` campaign completes, writes a scorecard per season, a track record with 2 rows, at least one changelog entry; Review Focus 4: FakeLLM returning only DISCARD verdicts → `selector_fallback` event and `buy_hold_spy` book; stop() between turns ends the season with `stopped=True`.
- [ ] Run, fail, implement, pass. Run the real thing: `uv run python -m aitrader campaign --quick` against Ollama and fix prompt or parsing issues until it completes. Commit `feat: orchestrator, selector, scorer and CLI`.

### Task 10: Web server and live page

**Files:**
- Create: `aitrader/web/__init__.py`, `aitrader/web/server.py`, `aitrader/web/static/index.html` (adapted from `docs/mockups/mission-control.html`), `tests/test_web.py`

**Interfaces:**
- Produces: `GET /` static page; `GET /api/status` (ollama ok, model, data manifest, campaign id, season, phase, agent, budget used/max, running flag); `POST /api/campaign` body `{seasons, personas, quick, apply_mode, model}` starts a thread; `POST /api/control/{pause|resume|step|stop}`; `GET /api/events` SSE of `Event` JSON (with `Last-Event-ID` resume from trace offset); `GET /api/state` (seasons ladder, this-season figures, leaderboard, progress series, scorecard, season table); `GET /api/notebook`, `/api/desk`, `/api/reviews`, `/api/changelog`, `/api/prompts/{agent}` (GET/PUT), `/api/strategy?ticker=`, `/api/runs`, `GET /api/runs/{id}/replay?speed=` (SSE from trace). Page: on load `GET /api/state` + `EventSource('/api/events')`; feed rows from events; panels refresh from `/api/state` on `season_scored`, `phase`, `change_applied`, else every 5 s while running; the walkthrough text is kept and each Next shows the next phase's events.

- [ ] Tests with FastAPI TestClient and a pre-built `runs/` fixture from Task 9's quick campaign: status 200 with keys; state has `seasons` and `track_record`; replay SSE yields the same number of events as lines in `trace.jsonl`; prompts PUT appends a changelog entry with `lever="manual_edit"`.
- [ ] Run, fail, implement, pass. Start `uv run python -m aitrader serve`, run a quick campaign from the page, watch the feed. Commit `feat: FastAPI server, SSE events and live Mission Control page`.

### Task 11: Full run, recorded replay, docs, slides, PR

**Files:**
- Modify: `README.md` (quickstart, hardware table, practices, status), `.gitignore` (keep `runs/recorded/` tracked), create `runs/recorded/` with one campaign's trace and state for Replay; rebuild `docs/slides/` with real screenshots and real numbers via `docs/slides/build_deck.py`.

- [ ] Run the default 6-season campaign with `qwen3:8b` on this machine (about 20 minutes). Fix anything that breaks. Save its `runs/<id>` as `runs/recorded/campaign-default`.
- [ ] Update README status; `uv run pytest -q -m "not network"` green.
- [ ] Rebuild the deck (v1.2 in the masterclass folder and `docs/slides/`) with screenshots of the live page and the real track record; remove "landing this week" wording.
- [ ] Commit, push branch, open draft PR against `master`.
