# aiInvesting: an AI investment team you can run on your laptop

A teaching lab for the question **"How well can an AI investment team trade, and does it get better with feedback?"**

Everything runs locally with [Ollama](https://ollama.com) and an open-weight model. **No API keys, no paid services, no cloud.** Free daily market data from `yfinance`. MIT licensed.

Built for the *AI and Agentic AI in Finance* masterclass at Johns Hopkins (Oct 24, 2026) by Professor Jim Kyung-Soo Liew.

## What is in the repo today

| Path | What it is |
|---|---|
| `docs/superpowers/specs/2026-10-22-ai-trading-agents-design.md` | The full design spec: agent roster, phases, schemas, the coach's lever menu, budgets, error handling, test plan, two-day build schedule |
| `docs/mockups/mission-control.html` | The dashboard, "Mission Control", as a single self-contained HTML file with sample data. Open it in any browser. It starts in a 17-step guided walkthrough |
| `docs/slides/` | The masterclass section about this project as PowerPoint and PDF |

The Python package (`aitrader/`) is landing in this repo during the week of Oct 24, 2026, following the spec. Until then the mockup shows what it will look like and the spec says how it works.

## The idea in one minute

Seven specialised agents form an **investment team**. A plain Python orchestrator runs them in fixed phases over rolling **seasons** (one calendar quarter each, never seen before):

1. **Research.** An Idea Agent proposes hypotheses, a Coder Agent writes `generate_signals()`, a sandbox and a lookahead guard check the code, the engine backtests it on train and validation windows, a Critic Agent votes Keep or Discard.
2. **Select.** Plain code picks the best validation Sharpe under a turnover cap. That strategy is the season's *quant book*.
3. **Trade.** The quant book trades mechanically through the sealed quarter while a trader persona makes weekly BUY / SELL / HOLD calls from a point-in-time snapshot.
4. **Score.** Quant book, desk, the team (half each), SPY and baselines. The track record grows by one quarter.
5. **Review.** A Review Agent, the coach, reads the season and recommends 1 to 3 changes, but only from a fixed menu of levers. Every change is logged with a revert condition.
6. **Apply** and start the next season.

Rolling seasons mean each quarter is traded exactly once, out of sample, and only then becomes history the team may learn from. That is what stops the feedback loop from peeking at the future.

## Assumptions

- **Data:** `yfinance`, daily bars from 2015, free and keyless. It is an unofficial interface to Yahoo Finance; use it for personal and educational purposes and expect occasional gaps. The Data Agent checks and reports them.
- **Model:** Ollama with `qwen3:8b` by default (open weights, Apache 2.0). Supports tool calling and JSON-schema output. `qwen3:4b` fits 8 GB laptops; `qwen3:14b` writes better code on 32 GB.
- **Market model:** 12 US large caps plus SPY as the benchmark the team never holds. Long only, daily closes, weekly rebalance, 5 basis points per unit of weight traded. No shorting, leverage, options or intraday data in v1.
- **Compute:** about 2 to 5 seconds per model call on Apple Silicon. A six-season campaign is roughly 220 calls, about 20 minutes. The dashboard's Replay mode shows a recorded run when live is too slow for class.

This is a lab for agent engineering and honest evaluation. **It is not investment advice.**

## Quickstart (once the package lands)

```bash
ollama pull qwen3:8b
git clone https://github.com/jimkliew/aiInvesting.git && cd aiInvesting
uv run python -m aitrader serve          # open http://localhost:8000 and click Run campaign
```

Until then:

```bash
open docs/mockups/mission-control.html   # the dashboard with sample data
```

## Agent engineering practices the code demonstrates

Tools compute while the model reasons; small typed tools; schema-enforced outputs with retries; bounded loops and budgets; a JSONL trace of every event, replayable; no lookahead by construction; sandboxed model-written code; evaluation first with train, validation and sealed seasons; reproducibility; a lab notebook and per-agent lessons as memory; human in the loop; workflows over free-form agents; rolling out-of-sample evaluation; bounded self-improvement through a lever menu.

Each is named in the spec with the file that will implement it.

## No secrets, by design

Nothing in this repo needs a key, so there is nothing to leak. `.gitignore` excludes generated data and run folders.

## License

MIT. See `LICENSE`.
