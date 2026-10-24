# aiInvesting: an AI investment team you can run on your laptop

A teaching lab for one question: **how well can an AI investment team trade, and does it get better with feedback?**

Everything runs locally with [Ollama](https://ollama.com) and an open-weight model. **No API keys, no paid services, no cloud.** Free daily market data from `yfinance`. MIT licensed.

Built for the *AI and Agentic AI in Finance* masterclass at Johns Hopkins (Oct 24, 2026) by Professor Jim Kyung-Soo Liew.

## Quickstart

```bash
ollama pull qwen3:8b                      # once; any Ollama model works with --model
git clone https://github.com/jimkliew/aiInvesting.git && cd aiInvesting
uv run python -m aitrader status          # checks Ollama and the model
uv run python -m aitrader serve           # Mission Control at http://localhost:8000
```

Click **Run campaign** on the page, or from the command line:

```bash
uv run python -m aitrader campaign --quick               # 3 tickers, 1 idea, 2 short seasons: about 2 minutes
uv run python -m aitrader campaign                       # 12 tickers + SPY, 6 quarterly seasons: about 20 to 30 minutes
uv run python -m aitrader campaign --personas momentum,contrarian --apply approve
uv run python -m aitrader replay runs/<campaign> --speed 5
uv run python -m aitrader backtest                       # the classic baselines over the full history
uv run pytest                                            # 52 offline tests; add -m network for the yfinance one
```

`uv` creates the environment and installs everything on first run. Needs Python 3.11 or newer; `.python-version` pins 3.12.

## The idea in one minute

Seven specialised agents form an **investment team**. A plain Python orchestrator runs them in fixed phases over rolling **seasons**, one calendar quarter each, that the team has never seen:

1. **Research.** The Idea Agent proposes hypotheses; the Coder Agent writes `generate_signals()`; a sandbox, a lookahead guard, an exposure check and a turnover limit send bad code back with the reason; the engine backtests on train and validation windows; the Critic Agent votes Keep or Discard.
2. **Select.** Plain code re-runs every kept strategy, plus the classic baselines, on the validation year and picks the best Sharpe under a turnover cap. That is the season's *quant book*.
3. **Trade.** The quant book trades mechanically through the sealed quarter while a trader persona makes a BUY / SELL / HOLD call per stock at each rebalance from a point-in-time snapshot.
4. **Score.** Quant book, desk, the team (half each), SPY and baselines. The track record grows by one quarter.
5. **Review.** The Review Agent, the coach, reads the season packet and recommends up to three changes, but only from a fixed menu of levers. Every change is logged with a revert condition.
6. **Apply**, then the next season starts.

Rolling seasons mean each quarter is traded exactly once, out of sample, and only then becomes history the team may learn from. That is what stops the feedback loop from peeking at the future.

## Mission Control

The page at `localhost:8000` shows the live feed of every agent turn, the season ladder, this season's figures, and tabs for Progress (track record with change flags, excess return per season, did validation predict the season), Strategy (the book's code and what it did on one ticker), Notebook, Desk, Reviews (with Accept / Reject in ask-me mode), Changelog, Prompts (editable), Processes and Runs (open or replay any campaign). Press **Walkthrough** for a 17-step guided tour that reveals the feed stage by stage.

## Map of the code and the agents

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): one diagram of every part, the season flow phase by phase, a table of the agents (prompt, inputs, outputs, tools), the deterministic core, what lands on disk, and where to change things.

## Layout

```
aitrader/
  __main__.py        CLI: status, fetch, backtest, campaign, serve, replay
  orchestrator.py    the state machine: campaign -> seasons -> phases; budgets; pause/step/stop
  llm.py             Ollama wrapper: schema-constrained JSON with retries, tool loop, budget
  agents/            data, idea, coder, critic, trader (3 personas), review
  prompts/           one .md per agent; coach lessons are appended at call time
  levers.py          the only way the coach can change the team
  seasons.py         quarter calendar, train / validation / season windows
  store.py           runs/<campaign>/: trace.jsonl, notebook, lessons, changelog, track record
  data/              yfinance fetch + parquet cache, quality checks, features, snapshot, manifest
  backtest/          engine, metrics, baselines, sandbox (subprocess), lookahead guard, selector, scorer
  web/               FastAPI server, SSE events, static/index.html
docs/superpowers/    design spec and implementation plan
docs/mockups/        the standalone dashboard mockup with sample data
docs/slides/         the masterclass section as PowerPoint and PDF
```

## Assumptions

- **Data:** `yfinance`, daily adjusted closes from 2015, free and keyless. It is an unofficial interface to Yahoo Finance; use it for personal and educational purposes and expect the occasional gap. The Data Agent checks and reports them.
- **Model:** Ollama with `qwen3:8b` by default (open weights, Apache 2.0). Supports tool calling and JSON-schema output. `qwen3:4b` fits 8 GB laptops; `qwen3:14b` writes better code on 32 GB.
- **Market model:** 12 US large caps plus SPY as the benchmark the team never holds. Long only, daily closes, one-bar execution lag, 5 basis points per unit of weight traded, monthly desk rebalance by default (weekly is a coach lever). No shorting, leverage, options or intraday data.
- **Compute:** about 2 to 5 seconds per model call on Apple Silicon. A six-season campaign is roughly 300 calls.

This is a lab for agent engineering and honest evaluation. **It is not investment advice.**

## Agent engineering practices the code demonstrates

Tools compute while the model reasons; small typed tools; schema-enforced outputs with retries; bounded loops and budgets; a JSONL trace of every event, replayable; no lookahead by construction; sandboxed model-written code; evaluation first with train, validation and sealed seasons; reproducibility; a lab notebook and per-agent lessons as memory; human in the loop; workflows over free-form agents; rolling out-of-sample evaluation; bounded self-improvement through a lever menu.

## No secrets, by design

Nothing in this repo needs a key, so there is nothing to leak. `.gitignore` excludes fetched data and run folders.

## License

MIT. See `LICENSE`.
