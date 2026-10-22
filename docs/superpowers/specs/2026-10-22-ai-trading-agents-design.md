# AI Trading Agents Lab — Design Spec

**Date:** 2026-10-22 (rev 3: seasons, Review Agent, feedback loop, Progress panel)
**Status:** Draft for review
**Owner:** Jim Liew
**Build window:** 2 days (2026-10-23 → 2026-10-24)

---

## 1. Purpose

A teaching repo that lets students answer one question with their own experiments:

> **How well can an AI investment team trade, and does it get better with feedback?**

Everything runs locally. The only requirement is [Ollama](https://ollama.com) and
an open-weight model. **No API keys, no paid services, no cloud.**

Students get a small, fixed **swarm of specialised agents** (the "investment
team"), a deterministic harness that scores the team honestly on **rolling
out-of-sample seasons**, a **Review Agent** that studies each season and
recommends improvements, and a **local web page ("Mission Control")** that
records every step and charts whether the team is improving.

The repo is as much about **agent engineering best practices** as about trading.
Every practice is named in the code and README so students can point to it.

## 2. What was said vs. what is assumed

**Stated by Jim**

- Students must be able to run it with nothing but Ollama. Free, open-source models.
- One agent gathers data; after that, agents back-test strategies.
- Use agent best practices. A swarm, but kept under control.
- A web page to run through everything during the online course.
- The page records what happens at each step and how successful the team is.
- A review agent analyses results and recommends improvements → a feedback loop.
- The page shows progress and whether the team is improving.
- See what can be built in the next 2 days.

**Assumptions (correct me)**

| # | Assumption | Why |
|---|---|---|
| A1 | US equities + ETFs, **daily bars**, via `yfinance` (no key). | Free, reliable, familiar to finance students. |
| A2 | Default universe: ~12 liquid names + SPY benchmark, 2015-01-01 → today. Fixed across seasons. | Comparable seasons; small enough for a laptop. |
| A3 | **Long-only**, target weight per asset in [0, 1], weekly rebalance for the desk, flat cost in basis points. No shorting or leverage in v1. | Keeps the engine ~150 lines. Shorting is a student exercise. |
| A4 | Default model **`qwen3:8b`** (already on this machine). `--model` flag to swap. | Tool calling + JSON-schema output verified today. Fits 16 GB laptops. |
| A5 | Python 3.11+ managed with **`uv`**, CLI + local web UI. | One-command setup. |
| A6 | Students are finance-literate, mixed coding skill. | Readable code over clever code. |
| A7 | Private machines; LLM-written strategy code is still sandboxed. | Worth teaching even if the risk is low. |
| A8 | Web page runs on `localhost`; Jim screen-shares it; students run their own copy later. | No hosting, no auth, nothing to pay for. |
| A9 | A "season" is **one calendar quarter** of out-of-sample trading; default run is 6 seasons (2025-Q1 → 2026-Q2). | ~13 weekly decisions per season; enough seasons to draw a progress line, few enough to finish in class. |
| A10 | The Review Agent's recommendations are **applied automatically by default**, with an approve-mode toggle for class. | Demonstrates the closed loop; approve-mode demonstrates human-in-the-loop. |

## 3. Environment verified today (2026-10-22)

| Check | Result |
|---|---|
| Ollama | 0.40.4 running; `qwen3:8b` pulled |
| Tool calling with qwen3:8b | Works; correct tool + arguments first try (4.5 s incl. load) |
| JSON-schema structured output | Works; valid `{action, confidence, reason}` in 1.9 s |
| `uv pip install yfinance pandas numpy ollama pyarrow matplotlib` | Installs clean (uv picked Python 3.12) |
| `yfinance` SPY download | 41 rows for Jan–Feb 2024 in 0.6 s, no key |
| Hardware | Mac Studio M4 Max, 36 GB |

Implication: ~2–5 s per LLM call. Budget math is in §6.8.

## 4. Approaches considered

**Agent layer — A. Hand-rolled minimal runtime on the `ollama` client (RECOMMENDED).**
We write the loop ourselves (~200 lines): send goal + tool schemas → run any
tool the model calls → repeat until a final answer or the step budget runs out.
Plus `@tool`, `structured(schema)` with retries, and a JSONL trace writer.
Students see everything; nothing breaks when a framework changes.
*B. PydanticAI* (lighter framework; offered as a student exercise).
*C. LangGraph* (heavy, churny; not chosen).

**Backtester —** small in-repo vectorized engine, not `vectorbt`/`backtrader`.

**Evaluation — rolling out-of-sample seasons (walk-forward), not one fixed test set.**
With a feedback loop, a single fixed test set would be burned the first time
the Review Agent saw it. Rolling seasons solve this: each quarter is traded
exactly once, out of sample, then becomes history the team may learn from.
This is also how real teams are judged — by a track record.

**Web UI —** FastAPI + one static HTML page + Server-Sent Events, not Streamlit
(its rerun model fights long-running jobs and live streaming).

## 5. Agent best practices this repo demonstrates

| # | Practice | Where it lives |
|---|---|---|
| P1 | **LLM reasons, tools compute.** The model never does arithmetic or touches raw DataFrames. | `aitrader/tools/*` |
| P2 | **Small, typed, documented tools** (≤ 4 per agent) returning compact text/JSON. | `@tool` in `agent.py` |
| P3 | **Structured outputs enforced by schema**, validated by pydantic, retried with the error fed back. | `llm.py: structured()` |
| P4 | **Bounded loops**: max steps, wall-clock budget, tool-call cap, global LLM-call budget per season. | `agent.py`, `orchestrator.py` |
| P5 | **Observability**: every season gets an id; every prompt, tool call, output and decision goes to `trace.jsonl`, streams to the UI, and stays browsable after restart. | `events.py`, `web/` |
| P6 | **Guardrail — no lookahead.** Data is sliced *as-of* the season cutoff before any agent sees it; engine lags execution one bar; a perturbation test proves a strategy didn't peek. | `backtest/lookahead.py` |
| P7 | **Guardrail — sandboxed code.** LLM-written code runs with an AST allowlist, restricted builtins, time limit. | `backtest/sandbox.py` |
| P8 | **Evaluation-first.** Train / validation / season split per season; agents see train+val only; the season is scored once. Strategies tried are counted. | `backtest/splits.py` |
| P9 | **Reproducibility.** Temperature 0, pinned model tag, dataset hash, prompts stored with results, every season replayable. | `data/manifest.json`, `runs/` |
| P10 | **Memory.** Lab notebook (strategies + results) and per-agent *lessons* persist across seasons. | `store.py` |
| P11 | **Human-in-the-loop.** Step mode; approve-mode for Review recommendations; students grade. | `web/` |
| P12 | **Small-model ergonomics.** Short prompts, one decision per call, worked examples, `think=False`, info-in-prompt over tool-fetching. | `aitrader/prompts/` |
| P13 | **Graceful degradation.** `--no-llm` deterministic path; Replay mode when live is slow. | CLI, `web/` |
| P14 | **Workflows over free-form agents.** The orchestrator is code. Agents do judgment inside fixed phases. | `orchestrator.py` |
| P15 | **Typed hand-offs, not chat.** Agents read/write pydantic artifacts on a shared run store; no agent-to-agent conversation. | `store.py`, `schemas.py` |
| P16 | **Rolling out-of-sample evaluation.** Each season is used once, then becomes history. Improvement is measured on seasons the team had not yet seen. | `seasons.py` |
| P17 | **Bounded self-improvement.** The Review Agent chooses from a fixed menu of levers; every change is logged with rationale and expected effect; changes can be reverted. | `review_agent.py`, `levers.py` |

## 6. Architecture

```
aiInvesting/
├── pyproject.toml              # uv; deps: ollama pandas numpy yfinance pyarrow pydantic rich matplotlib fastapi uvicorn
├── README.md                   # quickstart + "Practices" + exercises
├── universe.yaml               # tickers, dates, costs, season calendar
├── aitrader/
│   ├── cli.py                  # python -m aitrader {fetch|backtest|season|campaign|serve|replay}
│   ├── llm.py                  # Ollama wrapper: chat(), structured(schema), health check, retries
│   ├── agent.py                # Agent base: @tool registry, bounded tool loop, event hook
│   ├── orchestrator.py         # state machine: campaign → seasons → phases; budgets; step/pause/stop
│   ├── seasons.py              # season calendar; train/val/season windows per season (expanding)
│   ├── levers.py               # the fixed menu of changes the Review Agent may request + apply/revert
│   ├── store.py                # run store: campaign/season folders, notebook, lessons, changelog, track record
│   ├── schemas.py              # pydantic: Hypothesis, StrategyCode, Review, Decision, Allocation, SeasonReview, Recommendation
│   ├── events.py               # Event dataclass, JSONL trace, in-process pub/sub
│   ├── prompts/                # data.md idea.md coder.md critic.md trader_momentum.md trader_contrarian.md trader_risk_averse.md pm.md review.md
│   ├── data/                   # fetch.py quality.py features.py manifest.py
│   ├── backtest/               # engine.py metrics.py splits.py strategies/ sandbox.py lookahead.py
│   ├── agents/                 # data_agent.py idea_agent.py coder_agent.py critic_agent.py trader_agent.py pm_agent.py review_agent.py
│   ├── report/                 # season_report.py progress.py (markdown + PNG)
│   └── web/
│       ├── server.py           # FastAPI: REST + SSE
│       └── static/             # index.html app.js style.css + vendored chart lib (offline)
├── data/                       # generated; git-ignored except manifest.json
├── runs/<campaign>/<season>/   # trace.jsonl, artifacts/, notebook.jsonl, report.md
├── runs/<campaign>/            # track_record.json, changelog.jsonl, lessons/, reviews/
├── tests/
└── notebooks/01_tour.ipynb     # optional
```

### 6.1 Vocabulary

| Term | Meaning |
|---|---|
| **Campaign** | One full experiment: N consecutive seasons with the feedback loop on. One row in the Runs tab. |
| **Season** | One calendar quarter traded out of sample. The team researches on data before the season, trades through it, then is reviewed. |
| **Team** | The fixed swarm of agents plus their current prompts, lessons and parameters. |
| **Team portfolio** | 50% **quant book** (the strategy selected on validation) + 50% **discretionary desk** (trader persona, or PM committee if enabled). Reported alongside both components and SPY. |
| **Track record** | The chained out-of-sample equity curve of the team portfolio across seasons. The headline "how successful is the team" number. |
| **Lever** | A change the Review Agent may request. Fixed menu (§6.6). |

### 6.2 Season windows

Expanding window. For season *s* starting at date *T*:

| Window | Dates | Who sees it |
|---|---|---|
| Train | 2015-01-01 → *T* − 12 months | Idea / Coder / Critic (via backtests) |
| Validation | *T* − 12 months → *T* | Critic + selector pick the quant book here |
| Season (OOS) | *T* → *T* + 1 quarter | Nobody, until traded. Then it is history. |

Default campaign: 6 seasons, 2025-Q1 → 2026-Q2. `--seasons N --start 2024-01-01` to change.

### 6.3 Phases inside one season

```
Phase 0  Data        Data Agent (first season only; later seasons reuse the cached dataset)
Phase 1  Research    Idea → Coder → Critic over R rounds × K ideas, sharing the lab notebook
                     Selector picks quant book = best KEEP strategy by validation Sharpe
Phase 2  Trading     Desk personas (and PM if enabled) make weekly decisions through the season
                     Quant book is traded mechanically through the season
Phase 3  Scoring     Deterministic: season metrics for quant book, desk, team portfolio, SPY, baselines
                     Track record and leaderboard updated
Phase 4  Review      Review Agent reads this season + history → SeasonReview + Recommendations
Phase 5  Apply       Levers applied (auto) or queued for approval (approve-mode) → next season
```

### 6.4 The team (agent roster)

| Agent | Phase | Reads | Writes (schema) | Tools |
|---|---|---|---|---|
| **Data Agent** | 0 | brief | dataset + `data/REPORT.md` | 4 |
| **Idea Agent** | 1 | feature catalog, lab notebook, its lessons | `Hypothesis[]` (K per round, across trend / mean-reversion / volatility / cross-sectional families) | none |
| **Coder Agent** | 1 | one `Hypothesis` (+ error feedback) | `StrategyCode` | none |
| **Critic Agent** | 1 | code, train/val metrics, notebook, its lessons | `Review {KEEP/DISCARD, concerns, suggestion}` | none |
| **Trader Agents × 3 personas** | 2 | as-of snapshot, persona lessons | `Decision {action, target_weight, confidence, reason}` | none |
| **PM Agent** (optional) | 2 | the three `Decision`s | `Allocation` | none |
| **Review Agent** | 4 | season scorecard, track record, changelog, prior reviews, notebook summary, desk transcript excerpts | `SeasonReview {assessment, what_worked, what_failed, recommendations[]}` | none |

Deterministic, not agents: orchestrator, backtester, sandbox, lookahead guard,
selector, scorer, lever applier, event bus, web server.

Only the Data Agent uses tool calling. The rest get everything in the prompt:
more reliable and cheaper for an 8B model, and a teaching point.

### 6.5 Review Agent and the feedback loop

The Review Agent is the team's coach. After each season it receives a compact
packet (≈ 1,500 tokens):

- this season's scorecard: quant book, desk, team, SPY, baselines; drawdown; turnover
- track record so far and the previous seasons' scorecards
- did validation predict out of sample? (val Sharpe of the chosen book vs its season Sharpe)
- the changelog: what was changed before this season and why
- notebook summary: strategy families tried, kept, discarded; failure reasons
- desk excerpts: the 3 best and 3 worst decisions with their stated reasons

It returns a `SeasonReview` with 1–3 `Recommendation`s. Each recommendation is:

```
lever            one of the fixed menu below
target           which agent / parameter
change           the concrete edit (≤ 300 chars for prompt lessons)
rationale        grounded in a number from the packet
expected_effect  which metric should move, which direction
revert_if        condition under which the next review should revert it
```

**Lever menu** (`levers.py`): the Review Agent may do nothing else.

| Lever | Example |
|---|---|
| `add_lesson(agent)` | append a ≤ 300-char lesson to a persona's / Idea Agent's / Critic's prompt |
| `remove_lesson(agent, id)` | drop a lesson that didn't help |
| `set_param(name, value)` | `research.rounds`, `research.ideas_per_round`, `desk.rebalance=weekly|monthly`, `desk.max_weight`, `critic.min_val_sharpe`, `selector.max_turnover` (each with a hard allowed range) |
| `set_family_focus(list)` | tell the Idea Agent which strategy families to emphasise or avoid |
| `retire_strategy(id)` / `reinstate_strategy(id)` | manage the quant book candidates |
| `set_persona_weights({...})` | if the committee is on, bias the PM toward a persona |
| `revert(change_id)` | undo an earlier change |

Everything else (universe, costs, data, season calendar, model) is frozen for
the campaign so seasons stay comparable.

**Apply modes:** `auto` (default) applies immediately and logs; `approve` queues
recommendations in the UI with Accept / Reject buttons. Every applied change
gets a `change_id`, appears in the changelog, and is marked on the progress
chart at the season where it took effect.

**Why this cannot leak the future:** the Review Agent only ever sees seasons
that have already been traded. The next season is new data to every agent.

**An honest caveat for the course:** with 6–8 seasons, season-to-season
differences are dominated by market regime and noise. The lab teaches the
*mechanics and measurement* of a feedback loop and lets students ask "did
validation predict out of sample?" and "did the Review Agent's changes help?"
It will not prove that LLMs learn to beat the market, and the README says so.

### 6.6 Research swarm detail (phase 1)

```
for round in 1..R:                               # default R=1 per season (2 in season 1)
    ideas = IdeaAgent(notebook, lessons, family_focus)       # K ideas, default 4
    for h in ideas:
        code = CoderAgent(h)
        for attempt in 1..3:
            ok, err = sandbox.compile_and_check(code)        # P7
            if ok and lookahead.passes(code): break           # P6
            code = CoderAgent(h, feedback=err)
        else: notebook.add(h, status="failed", err); continue
        m_train, m_val = backtest(code, train), backtest(code, val)
        review = CriticAgent(code, m_train, m_val, notebook, lessons)
        notebook.add(h, code, m_train, m_val, review)
quant_book = selector.pick(notebook, min_val_sharpe, max_turnover)   # validation only
```

Strategies persist in the notebook across seasons, so the team accumulates a
book of candidates; the selector re-evaluates all non-retired candidates on the
new validation window each season.

### 6.7 Trading desk detail (phase 2)

Weekly, for each rebalance date inside the season: build the as-of snapshot
(last 20 closes, SMA20/50/200 position, RSI14, 1/3/12-month returns, realized
vol, current weight, ~300 tokens) → `Decision` at temperature 0 → engine
executes next bar → rationale logged. Personas differ only by prompt file plus
their accumulated lessons. Default 1 persona; `--personas 3`; `--committee`
adds the PM.

### 6.8 Orchestrator, swarm rules and budgets

1. **Fixed roster.** Agents cannot spawn agents.
2. **Orchestrator is code.** Campaign → seasons → phases in fixed order.
3. **No agent-to-agent chat.** Typed artifacts on the run store only.
4. **One prompt file, one output schema, ≤ 4 tools, ≤ 3 retries** per agent.
5. **Budgets per season** (`max_llm_calls`, `max_minutes`, `max_strategies`) and per campaign; shown as meters; clean stop with partial results.
6. **Sequential by default.** One laptop serves one model; `--parallel 2` exists to prove the point.
7. **Everything replayable** from `trace.jsonl`.
8. **The Review Agent cannot touch anything outside the lever menu.**

Budget per season on M4 Max with `qwen3:8b` (2–5 s per call):

| Phase | Calls | Time |
|---|---|---|
| Research (1 round × 4 ideas) | ~20 | ~2 min |
| Desk (1 persona × 13 weeks) | 13 | ~1 min |
| Review | 2 | ~10 s |
| **Per season** | **~35** | **~3 min** |
| **Default campaign (6 seasons)** | **~220** | **~18 min** |
| Class demo (3 personas + committee, 6 seasons) | ~500 | ~40 min → use Replay |

Season 1 adds the Data Agent (≤ 12 calls) and a second research round.
An 8 GB laptop with `qwen3:4b` is 2–3× slower; students can run `--seasons 3`.

### 6.9 Web UI — "Mission Control"

**Stack:** FastAPI + uvicorn; one static `index.html` with vanilla JS/CSS;
Server-Sent Events for the live feed; a small MIT chart library vendored into
`static/` so it works offline. No npm, no build, no CDN.
`uv run python -m aitrader serve` → `http://localhost:8000`.

**Layout**

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ AI Trading Lab  ● Ollama qwen3:8b  ● Data 13 tickers 2015–2026  Campaign #3     │
│ Season 4/6 · Phase 2 Trading · LLM calls 112/220 · 11:40 · [Step][Pause][Stop]  │
├───────────────┬────────────────────────────────┬───────────────────────────────┤
│ CAMPAIGN      │ LIVE AGENT FEED                │ THIS SEASON                   │
│ S1 ✔ +1.2%    │ Trader(momentum) wk 7 → BUY    │ quant book  +2.1%  SPY +1.4%  │
│ S2 ✔ −0.8%    │   NVDA 0.25 conf 0.7 "above…"  │ desk        +0.9%             │
│ S3 ✔ +2.4%    │ Engine: filled next open       │ team        +1.5%             │
│ S4 ▶ Trading  │ Trader(momentum) wk 8 → HOLD   │ leaderboard ▸ (val | season)  │
│ S5 · queued   │ …                              │                               │
│ S6 · queued   │                                │ equity (season) ▁▂▃▅▆         │
├───────────────┴────────────────────────────────┴───────────────────────────────┤
│ [Progress] [Season] [Notebook] [Desk] [Reviews] [Changelog] [Prompts] [Runs]   │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Progress tab** (the "is it improving?" view)

- **Track record chart:** cumulative OOS equity of Team, quant book, desk, SPY across seasons; vertical season dividers; markers where Review changes took effect (hover → the change).
- **Season bars:** excess return vs SPY per season; a second series for "validation Sharpe of the chosen book" so students see whether validation predicted the season.
- **Scorecard:** seasons beating SPY (x of n), cumulative excess return, OOS Sharpe to date, max drawdown, strategies tried, lessons accumulated, LLM calls used.
- **Season table:** season · chosen strategy · val Sharpe · season return · SPY · excess · desk · review verdict · changes applied.

**Other tabs**

| Tab | Contents |
|---|---|
| Season | Full leaderboard for the current season (validation and season columns), equity curves, the chosen strategy's hypothesis + code |
| Notebook | Every strategy ever tried: family, hypothesis, val/season metrics, Critic verdict, status |
| Desk | Every weekly decision with snapshot, action, confidence and stated reason; filter by persona; best/worst flagged |
| Reviews | Each season's `SeasonReview`: assessment, what worked, what failed, recommendations and their status (applied / rejected / reverted) |
| Changelog | Numbered changes with lever, target, rationale, expected effect, season applied, observed effect so far |
| Prompts | Current prompt + lessons per agent; edit, save, mark "manual change" in the changelog |
| Runs | Previous campaigns; open any; Replay at 1× / 5× / instant; compare two campaigns' track records (P2) |

**Classroom controls:** Run campaign / Run one season / Step / Pause / Stop;
approve-mode toggle (recommendations wait for Accept / Reject); Replay. The repo
ships with one recorded campaign so the class demo never depends on live speed.

**API**

```
GET  /api/status                       ollama, dataset, campaign, season, phase, budgets
POST /api/campaign  {seasons, personas, committee, apply_mode, model}
POST /api/season                       run just the next season
POST /api/control/{step|pause|resume|stop}
GET  /api/events                       SSE: Event{ts, campaign, season, phase, agent, kind, payload}
GET  /api/progress                     track record, season table, scorecard, change markers
GET  /api/season/{n}                   leaderboard, equity, chosen strategy, decisions
GET  /api/reviews  /api/changelog  /api/notebook  /api/desk
POST /api/recommendations/{id}/{accept|reject}
GET  /api/prompts/{agent}   PUT
GET  /api/runs  /api/runs/{id}/replay?speed=5
```

The orchestrator publishes `Event`s to an in-process queue **and** `trace.jsonl`;
live SSE and Replay read the same shape, so the UI has one code path.

## 7. Error handling

| Failure | Behaviour |
|---|---|
| Ollama not running / model missing | Health check (CLI and UI banner) with the exact `ollama serve` / `ollama pull` command. |
| `yfinance` rate limit / network | 3 retries with backoff; parquet cache; quality report flags stale data. |
| Invalid JSON / schema | Up to 3 retries with the validation error appended; then `AgentError`, logged, phase continues. |
| LLM strategy code raises / times out | Sandbox catches; traceback → Coder feedback (≤ 3 attempts) → marked failed. |
| Lookahead detected | Attempt rejected, reason fed back, counted. |
| Review Agent asks for a lever outside the menu or out of range | Rejected by `levers.py`, logged as `invalid_recommendation`, season continues. |
| Budget exceeded | Clean stop of the phase or season; partial results kept; UI shows `budget_exceeded`. |
| Browser disconnects | SSE client reconnects and replays missed events from the trace offset. |
| Crash mid-campaign | Each season is checkpointed; `--resume` continues from the last completed season. |

## 8. Testing

- **Unit (no Ollama):** engine 5-bar known-answer; metrics; season window math; sandbox rejections; lookahead catch; manifest hash; lever range validation; revert restores prior state; budget stop.
- **Agent logic (mocked LLM):** `FakeLLM` returns canned outputs; a 2-season campaign runs end-to-end in < 10 s, produces a track record, a changelog with one applied and one reverted change.
- **Web:** `TestClient` — status, start mocked campaign, SSE events arrive, progress endpoint matches store, accept/reject recommendation, replay equals live.
- **Live (opt-in, `pytest -m ollama`):** one season, 2 tickers, 1 round, 1 idea, 1 persona.
- **Sanity:** buy-and-hold SPY matches a hand calculation from the parquet.

## 9. Two-day build schedule with priorities

P0 = must ship, P1 = should, P2 = stretch.

**Day 1 — foundation**

| Block | Deliverable | Pri |
|---|---|---|
| AM | Scaffold, `pyproject`, CLI, `schemas.py`, `events.py`, `store.py`, `seasons.py`; `data/` fetch + quality + features + manifest; tests | P0 |
| PM | `backtest/` engine + metrics + splits + 4 baselines; season scoring; track record math; `aitrader backtest` end-to-end | P0 |
| Late | `llm.py`, `agent.py`, `orchestrator.py` with season loop and budgets; Data Agent; README quickstart | P0 |

**Day 2 — team, coach, Mission Control**

| Block | Deliverable | Pri |
|---|---|---|
| AM | `sandbox.py`, `lookahead.py`; Idea / Coder / Critic + notebook + selector; one Trader persona; mocked-LLM season test | P0 |
| AM | `levers.py` + Review Agent + auto-apply + changelog | P0 |
| PM | `web/`: status bar, campaign rail, live feed, This-Season panel, **Progress tab** (track record chart, season table, scorecard), Replay | P0 |
| PM | Reviews, Changelog, Notebook, Desk tabs; approve-mode; two more personas; Step mode | P1 |
| Late | Run a 6-season default campaign; record it for Replay; write findings + exercises; tag `v0.1` | P0 |
| — | PM committee, Prompts tab editing, compare campaigns, crypto, model comparison, notebook tour | P2 |

**Main risk:** scope. The feedback loop and the Progress tab are the heart of
what Jim asked for, so they are P0; the secondary tabs are P1 and can slip to
day 3 without hurting the class story. Replay guarantees a working demo.

## 10. Student experience

```bash
ollama pull qwen3:8b
git clone <repo> && cd aiInvesting
uv run python -m aitrader serve                 # open http://localhost:8000 → "Run campaign"
# CLI equivalents
uv run python -m aitrader fetch "12 large-cap US tech names plus SPY, 2015 to today"
uv run python -m aitrader campaign --seasons 6 --personas 1
uv run python -m aitrader replay runs/<campaign> --speed 5
```

| Laptop RAM | Model | Notes |
|---|---|---|
| 8 GB | `qwen3:4b` | Slower; run `--seasons 3`; use Replay in class |
| 16 GB | `qwen3:8b` (default) | Verified |
| 32 GB+ | `qwen3:14b` | Better code, ~2× slower |

**Exercises:** switch to approve-mode and overrule the coach; add a lever;
edit a persona prompt and compare campaigns; add shorting; add an RSS news tool;
port the Coder Agent to PydanticAI; tighten the sandbox; test whether
validation Sharpe predicted season Sharpe; fact-check a `SeasonReview`.

## 11. Out of scope for v1

Live trading, broker APIs, intraday data, options, portfolio optimisation,
hosted deployment, authentication, any keyed or paid service, dynamic agent
spawning, letting the Review Agent change the universe, costs, data or model.

## 12. Open decisions for Jim

1. **Agent layer:** hand-rolled on the `ollama` client (recommended) vs PydanticAI.
2. **Scope:** daily US equities, long-only, ~12 tickers + SPY — OK?
3. **Seasons:** quarterly, 6 by default (2025-Q1 → 2026-Q2) — OK? Monthly seasons give more data points but noisier and 3× the LLM calls.
4. **Team portfolio definition:** 50/50 quant book + discretionary desk as the headline — OK, or headline just one of them?
5. **Apply mode default:** auto (closed loop) vs approve (you click Accept in class).
6. **Web UI stack:** FastAPI + single HTML page with SSE (recommended) vs Streamlit.
7. **Default model:** `qwen3:8b` — OK?
8. **Hosting:** GitHub org/repo name students will clone from.
