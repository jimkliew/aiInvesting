"""Draw docs/architecture.png: the parts of aitrader and how a season flows. No network, no mermaid.

Run: uv run python docs/draw_architecture.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

NAVY, INK, INK2, GREY = "#0B1F33", "#1b2430", "#56606e", "#8a929d"
BLUE, BLUE_SOFT, LINE, PAPER, PANEL = "#1c5cab", "#e3edf9", "#d6dad2", "#f4f5f3", "#fbfbfa"
ORANGE_SOFT, GREEN_SOFT, YELLOW_SOFT = "#fde8dc", "#d9f3e8", "#fff1c8"
FONT = ["Avenir Next", "DejaVu Sans"]


def box(ax, x, y, w, h, title, sub="", fill=PANEL, edge=LINE, title_size=11, sub_size=9, bold=True, radius=0.12, title_color=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}", linewidth=1.1, edgecolor=edge, facecolor=fill))
    cy = y + h / 2
    if sub:
        ax.text(x + w / 2, y + h - 0.26, title, ha="center", va="center", fontsize=title_size, fontweight="bold" if bold else "normal", color=title_color, family=FONT)
        ax.text(x + w / 2, y + (h - 0.42) / 2, sub, ha="center", va="center", fontsize=sub_size, color=INK2, family=FONT, linespacing=1.35)
    else:
        ax.text(x + w / 2, cy, title, ha="center", va="center", fontsize=title_size, fontweight="bold" if bold else "normal", color=title_color, family=FONT)


def arrow(ax, p0, p1, style="-|>", dashed=False, color=INK2, lw=1.3, rad=0.0, label=None, label_dy=0.12):
    a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=12, linewidth=lw, color=color,
                        linestyle=(0, (4, 3)) if dashed else "-", connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2)
    ax.add_patch(a)
    if label:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        ax.text(mx, my + label_dy, label, ha="center", va="bottom", fontsize=8.5, color=INK2, family=FONT,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))


def band(ax, x, y, w, h, label, fill=PAPER):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.14", linewidth=1, edgecolor=LINE, facecolor=fill))
    ax.text(x + 0.18, y + h - 0.22, label, ha="left", va="top", fontsize=9.5, color=BLUE, fontweight="bold", family=FONT)


def draw_parts(ax):
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 11.2)
    ax.axis("off")
    ax.text(0.2, 10.95, "How aitrader fits together", fontsize=15, fontweight="bold", color=NAVY, family=FONT, va="top")
    ax.text(0.2, 10.5, "Six agents do the judgment. Plain Python does the schedule, the arithmetic and the bookkeeping. "
                       "Agents never talk to each other; they read and write typed artifacts in the run store.",
            fontsize=9.5, color=INK2, family=FONT, va="top")

    # you
    box(ax, 0.3, 8.75, 3.0, 0.9, "python -m aitrader", "__main__.py: status, fetch, backtest,\ncampaign, serve, replay")
    box(ax, 3.7, 8.75, 3.4, 0.9, "Mission Control page", "web/static/index.html, one file")
    box(ax, 7.6, 8.75, 2.9, 0.9, "web/server.py", "REST + Server-Sent Events")
    arrow(ax, (7.1, 9.2), (7.6, 9.2))
    # orchestrator
    box(ax, 11.0, 8.6, 4.7, 1.2, "orchestrator.py", "the state machine, plain code\ncampaign → seasons → phases, pause / step / stop", fill=BLUE_SOFT, edge=BLUE)
    arrow(ax, (10.5, 9.2), (11.0, 9.2))
    arrow(ax, (1.8, 8.75), (1.8, 8.25), style="-")
    ax.plot([1.8, 13.35], [8.25, 8.25], color=INK2, lw=1.3)
    arrow(ax, (13.35, 8.6), (13.35, 8.25), style="-")

    # agents band
    band(ax, 0.3, 5.55, 15.4, 2.55, "AGENTS: judgment. One prompt file, one output schema, at most four tools, three retries")
    agents = [("Data Agent", "agents/data_agent.py\nbrief → dataset + report\n4 tools", GREEN_SOFT),
              ("Idea Agent", "agents/idea_agent.py\nnotebook → Hypotheses", "#e9e4fb"),
              ("Coder Agent", "agents/coder_agent.py\nhypothesis → generate_signals()", ORANGE_SOFT),
              ("Critic Agent", "agents/critic_agent.py\nmetrics → KEEP / DISCARD", YELLOW_SOFT),
              ("Trader personas", "agents/trader_agent.py\nsnapshot → Decision\nmomentum, contrarian, risk averse", "#dcecfb"),
              ("Review Agent", "agents/review_agent.py\nseason packet → SeasonReview\nthe coach", "#fbe0ea")]
    w, gap, x0, y0, h = 2.35, 0.21, 0.5, 6.3, 1.25
    xs = []
    for i, (t, s, f) in enumerate(agents):
        x = x0 + i * (w + gap)
        xs.append(x + w / 2)
        box(ax, x, y0, w, h, t, s, fill=f, edge=LINE, title_size=10.5, sub_size=8)
        arrow(ax, (x + w / 2, 8.25), (x + w / 2, y0 + h), style="-|>", lw=1.0)
    # llm
    box(ax, 0.5, 5.7, 15.0, 0.52, "llm.py → Ollama on your machine (qwen3:8b).  Schema-constrained JSON, validated by pydantic, retried with the error, counted against a budget.",
        fill=PANEL, title_size=9.5, bold=False)
    for cx in xs:
        arrow(ax, (cx, y0), (cx, 6.22), style="-|>", lw=0.9, color=GREY)

    # deterministic core band
    band(ax, 0.3, 2.35, 15.4, 2.95, "DETERMINISTIC CORE: arithmetic, schedule and guardrails. Never calls the model.")
    core = [("backtest/sandbox.py", "AST allowlist, subprocess,\ntime limit"),
            ("backtest/lookahead.py", "withhold 60 days;\nsignals must not change"),
            ("backtest/engine.py + metrics.py", "one-bar lag, 5 bp cost,\nweekly cadence, Sharpe, drawdown"),
            ("backtest/selector.py", "best validation Sharpe\nunder a turnover cap"),
            ("backtest/scorer.py", "book, desk, team (half each),\nSPY, baselines"),
            ("levers.py", "the only way the coach\nchanges the team; ranges; revert")]
    cw, cgap, cx0, cy0, ch = 2.35, 0.21, 0.5, 3.1, 1.3
    cxs = []
    for i, (t, s) in enumerate(core):
        x = cx0 + i * (cw + cgap)
        cxs.append(x + cw / 2)
        box(ax, x, cy0, cw, ch, t, s, fill=PANEL, title_size=9.5, sub_size=8)
    # flows into the core
    arrow(ax, (xs[2] - 0.6, y0), (cxs[0] + 0.2, cy0 + ch), dashed=True, rad=0.25, label="code", label_dy=0.0)
    arrow(ax, (cxs[0] + cw / 2, cy0 + ch / 2), (cxs[1] - cw / 2, cy0 + ch / 2))
    arrow(ax, (cxs[1] + cw / 2, cy0 + ch / 2), (cxs[2] - cw / 2, cy0 + ch / 2))
    arrow(ax, (xs[5] + 0.6, y0), (cxs[5], cy0 + ch), dashed=True, rad=-0.25, label="recommendations", label_dy=0.0)
    ax.text(cx0 + 3 * (cw + cgap) + 0.1, 2.62, "selector and scorer are called by the orchestrator between phases", fontsize=8, color=INK2, family=FONT)

    # store and events
    box(ax, 0.5, 0.45, 7.3, 1.45, "store.py  →  runs/<campaign>/", "campaign.json · params.json · notebook.jsonl · lessons.json · changelog.jsonl\ntrack_record.json · seasons/NN/ book, weights, decisions, scorecard, review",
        fill=PANEL, title_size=10.5, sub_size=8.3)
    box(ax, 8.2, 0.45, 7.3, 1.45, "events.py  →  trace.jsonl", "every prompt, tool call, decision and score as one line\nstreamed live to the page over SSE; Replay reads the same file",
        fill=PANEL, title_size=10.5, sub_size=8.3)
    ax.plot([cxs[5], cxs[5], 4.15], [cy0, 2.14, 2.14], color=INK2, lw=1.2)
    arrow(ax, (4.15, 2.14), (4.15, 1.9), style="-|>")
    ax.text(cxs[5] - 0.12, 2.19, "changes and lessons", fontsize=8, color=INK2, family=FONT, ha="right", va="bottom")
    ax.text(8.0, 0.18, "orchestrator.py writes every artifact to the store and every event to the trace; the server reads both and streams the trace to the page",
            fontsize=8.5, color=INK2, family=FONT, ha="center", va="bottom")


def draw_season(ax):
    ax.set_xlim(0, 16)
    ax.set_ylim(-0.15, 3.3)
    ax.axis("off")
    ax.text(0.2, 3.1, "One season, phase by phase (a season is one calendar quarter the team has never seen)", fontsize=12, fontweight="bold", color=NAVY, family=FONT, va="top")
    phases = [("Data", "season 1 only:\nfetch, check,\nmanifest hash", GREEN_SOFT),
              ("Research", "Idea → Coder → sandbox\n→ lookahead → engine → Critic\ndata up to the validation end", "#e9e4fb"),
              ("Select", "re-run kept strategies\nand baselines on validation;\nbest Sharpe under turnover cap", PANEL),
              ("Trade", "sealed quarter opens;\nbook trades weekly, persona\ndecides per stock at rebalance", "#dcecfb"),
              ("Score", "book, desk, team (½ each),\nSPY, baselines;\ntrack record += one quarter", PANEL),
              ("Review", "coach reads the packet,\nwrites ≤ 3 recommendations\nwith revert conditions", "#fbe0ea"),
              ("Apply", "levers.py: auto, or\nAccept / Reject;\nlogged with id", YELLOW_SOFT)]
    w, gap, x0, y, h = 2.0, 0.23, 0.3, 0.85, 1.65
    for i, (t, s, f) in enumerate(phases):
        x = x0 + i * (w + gap)
        box(ax, x, y, w, h, t, s, fill=f, title_size=10.5, sub_size=8)
        if i < len(phases) - 1:
            arrow(ax, (x + w, y + h / 2), (x + w + gap, y + h / 2))
    # loop back
    x_last = x0 + 6 * (w + gap) + w / 2
    x_first = x0 + 1 * (w + gap) + w / 2
    arrow(ax, (x_last, y), (x_first, y), style="-|>", rad=-0.11, dashed=True, color=INK2)
    ax.text((x_last + x_first) / 2, 0.0, "next quarter: the season just traded is now history the team may learn from", fontsize=8.5, color=INK2, family=FONT, ha="center", va="bottom")


def main(out="docs/architecture.png"):
    fig = plt.figure(figsize=(16, 14.5), dpi=150, facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[11.2, 3.3], hspace=0.02)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    draw_parts(ax1)
    draw_season(ax2)
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    print(out)
    # the two halves on their own, for slides
    stem = out[:-4] if out.endswith(".png") else out
    f1 = plt.figure(figsize=(16, 11.2), dpi=150, facecolor="white")
    draw_parts(f1.add_subplot(111))
    f1.savefig(stem + "_parts.png", dpi=150, bbox_inches="tight", facecolor="white")
    f2 = plt.figure(figsize=(16, 3.4), dpi=150, facecolor="white")
    draw_season(f2.add_subplot(111))
    f2.savefig(stem + "_season.png", dpi=150, bbox_inches="tight", facecolor="white")
    print(stem + "_parts.png", stem + "_season.png")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "docs/architecture.png")
