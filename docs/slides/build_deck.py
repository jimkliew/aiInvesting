"""Build the aiInvesting section of the masterclass deck in the style of an existing JHU deck.
Regenerate: python docs/slides/build_deck.py TEMPLATE.pptx out_v1.2.pptx docs/slides/aiInvesting-slides.pptx docs/slides/shots
The TEMPLATE is any deck using the same style kit; its original slides are dropped for the standalone output.
Usage: build_deck.py TEMPLATE OUT_V12 OUT_STANDALONE SHOTS_DIR
"""
import sys, math, copy
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
import json
from pathlib import Path

from PIL import Image

TEMPLATE, OUT_V12, OUT_SOLO, SHOTS = sys.argv[1:5]
RUN_DIR = sys.argv[5] if len(sys.argv) > 5 else None
pct = lambda v: ("+" if v > 0 else "\u2212" if v < 0 else "") + f"{abs(v):.1f}%"
REPO = "github.com/jimkliew/aiInvesting"

NAVY=RGBColor(0x0B,0x1F,0x33); GREY=RGBColor(0x66,0x70,0x85); BODY=RGBColor(0x24,0x34,0x47)
JHU=RGBColor(0x00,0x2D,0x72); LINE=RGBColor(0xDD,0xE3,0xEA); LIGHT=RGBColor(0xEE,0xF2,0xF6)
BLUE2=RGBColor(0x17,0x69,0xAA); GREEN=RGBColor(0x11,0x84,0x5B); WHITE=RGBColor(0xFF,0xFF,0xFF)
PALE=RGBColor(0xEA,0xF0,0xF6); MUTED=RGBColor(0x98,0xA2,0xB3); CODEBG=RGBColor(0xF6,0xF8,0xFA)
TITLE_FONT="Georgia"; BODY_FONT="Aptos"; MONO="Courier New"

# ---------- text fitting ----------
def est_lines(text, size_pt, width_in, mono=False):
    cw = (0.60 if mono else 0.50) * size_pt / 72.0   # avg char width in inches
    cpl = max(8, int((width_in - 0.12) / cw))
    n = 0
    for para in text.split("\n"):
        n += max(1, math.ceil(len(para) / cpl)) if para else 1
    return n
def fit_size(text, size_pt, width_in, height_in, mono=False, min_pt=7.5):
    s = size_pt
    while s > min_pt:
        h = est_lines(text, s, width_in, mono) * s * 1.22 / 72.0 + 0.10
        if h <= height_in: break
        s -= 0.5
    return s

# ---------- primitives ----------
def _set_font(run, size, bold, color, font, italic=False):
    run.font.name = font; run.font.size = Pt(size); run.font.bold = bold; run.font.italic = italic
    run.font.color.rgb = color

def tb(slide, x, y, w, h, paras, size=12, bold=False, color=BODY, font=BODY_FONT, align=None,
       anchor=MSO_ANCHOR.TOP, margin=0.05, fit=True, mono=False, space_after=0, line_spacing=None):
    """paras: str (\n-separated) or list of paragraphs; a paragraph is str or list of (text, bold, color|None)."""
    if isinstance(paras, str): paras = paras.split("\n")
    plain = "\n".join(p if isinstance(p, str) else "".join(r[0] for r in p) for p in paras)
    if fit: size = fit_size(plain, size, w, h, mono)
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(margin); tf.margin_top = tf.margin_bottom = Inches(0.03)
    tf.vertical_anchor = anchor
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if align is not None: para.alignment = align
        if space_after: para.space_after = Pt(space_after)
        if line_spacing: para.line_spacing = line_spacing
        runs = [(p, bold, None)] if isinstance(p, str) else p
        for text, b, c in runs:
            r = para.add_run(); r.text = text
            _set_font(r, size, b, c or color, font)
    return box

def rect(slide, x, y, w, h, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06, line_w=0.8):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE: s.adjustments[0] = radius
    if fill is None: s.fill.background()
    else: s.fill.solid(); s.fill.fore_color.rgb = fill
    if line is None: s.line.fill.background()
    else: s.line.color.rgb = line; s.line.width = Pt(line_w)
    s.shadow.inherit = False
    return s

def shape_text(s, text, size, bold, color, font=BODY_FONT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE):
    tf = s.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.08); tf.margin_top = tf.margin_bottom = Inches(0.03)
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph(); p.alignment = align
        r = p.add_run(); r.text = ln; _set_font(r, size, bold, color, font)

def oval(slide, x, y, d, text, fill=JHU, size=9):
    s = rect(slide, x, y, d, d, fill=fill, line=None, shape=MSO_SHAPE.OVAL)
    shape_text(s, text, size, True, WHITE); s.text_frame.margin_left = s.text_frame.margin_right = 0; return s

def card(slide, x, y, w, h, num, title, body, num_fill=JHU, title_size=13, body_size=11.5):
    rect(slide, x, y, w, h)
    d = 0.32
    oval(slide, x+0.18, y+0.18, d, str(num), fill=num_fill, size=9)
    tb(slide, x+0.18+d+0.10, y+0.14, w-0.18-d-0.22, 0.40, title, size=title_size, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
    tb(slide, x+0.18, y+0.62, w-0.36, h-0.74, body, size=body_size, color=BODY)

def label_card(slide, x, y, w, h, label, body, body_size=11):
    rect(slide, x, y, w, h)
    tb(slide, x+0.16, y+0.10, w-0.32, 0.24, label, size=9.5, bold=True, color=BLUE2)
    tb(slide, x+0.16, y+0.36, w-0.32, h-0.44, body, size=body_size, color=BODY)

def code_box(slide, x, y, w, h, code, label=None, size=9):
    rect(slide, x, y, w, h, fill=CODEBG, line=LINE)
    top = y + 0.08
    if label:
        tb(slide, x+0.14, top, w-0.28, 0.22, label, size=9.5, bold=True, color=BLUE2); top += 0.26
    tb(slide, x+0.14, top, w-0.28, y+h-top-0.08, code, size=size, color=NAVY, font=MONO, mono=True, margin=0.02)

def picture(slide, path, x, y, w, h, frame=True, valign="center"):
    im = Image.open(path); iw, ih = im.size
    sc = min(w/iw, h/ih); pw, ph = iw*sc, ih*sc
    px, py = x + (w-pw)/2, (y if valign == "top" else y + (h-ph)/2)
    if frame: rect(slide, px-0.04, py-0.04, pw+0.08, ph+0.08, fill=WHITE, line=LINE, radius=0.02)
    slide.shapes.add_picture(path, Inches(px), Inches(py), Inches(pw), Inches(ph))
    return px, py, pw, ph

def banner(slide, text, y=1.10, h=0.54):
    s = rect(slide, 0.55, y, 12.23, h, fill=NAVY, line=None, radius=0.12)
    shape_text(s, text, 13.5, False, WHITE, font=TITLE_FONT)

def light_banner(slide, x, y, w, h, text, size=12):
    s = rect(slide, x, y, w, h, fill=LIGHT, line=LINE, radius=0.08)
    shape_text(s, text, size, True, BLUE2)

def base(prs, num, title, subtitle, callout=None, footer=None):
    layout = next(l for l in prs.slide_layouts if l.name == "Blank")
    s = prs.slides.add_slide(layout)
    rect(s, 0, 0, 13.333, 0.10, fill=NAVY, line=None, shape=MSO_SHAPE.RECTANGLE)
    tb(s, 0.55, 0.29, 12.23, 0.46, title, size=22.5, bold=True, color=NAVY, font=TITLE_FONT, fit=False)
    tb(s, 0.55, 0.79, 12.23, 0.21, subtitle, size=11.25, color=GREY, fit=False)
    if callout: banner(s, callout)
    tb(s, 11.98, 7.21, 0.80, 0.15, str(num), size=7.5, color=GREY, align=PP_ALIGN.RIGHT, fit=False)
    if footer: tb(s, 0.55, 7.17, 11.04, 0.25, footer, size=7.5, color=GREY, fit=False)
    return s

def connector(slide, x1, y1, x2, y2):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = LINE; c.line.width = Pt(1.5); return c

# ---------- the section ----------
def build_section(prs, n0):
    n = n0
    sh = lambda name: f"{SHOTS}/{name}"

    # A. opener, in the style of "Today's Topics"
    layout = next(l for l in prs.slide_layouts if l.name == "Blank")
    s = prs.slides.add_slide(layout)
    tb(s, 0.53, 0.29, 10.2, 0.96, "Opensource your Quant Strategy", size=36, bold=True, color=NAVY, font=TITLE_FONT, anchor=MSO_ANCHOR.MIDDLE, fit=False)
    b = rect(s, 10.87, 0.37, 1.90, 0.42, fill=PALE, line=PALE); shape_text(b, "As of Oct 24, 2026", 9.3, True, NAVY)
    rect(s, 0.46, 1.62, 12.20, 4.64, fill=NAVY, line=NAVY, radius=0.02)
    tb(s, 0.79, 1.90, 11.45, 2.30, ["aiInvesting: an AI investment team", "you can run on your own laptop"], size=44, color=WHITE, font=TITLE_FONT, anchor=MSO_ANCHOR.MIDDLE, fit=False)
    tb(s, 0.79, 4.30, 11.45, 0.70, "No API keys. Free data. A free open-weight model. Everything open source.", size=22, color=RGBColor(0xCA,0xDC,0xFC), font=TITLE_FONT, fit=False)
    tb(s, 0.79, 5.15, 11.45, 0.80, ["Seven agents do the judgment. Plain Python does the schedule, the arithmetic and the bookkeeping.", "A coach reviews every quarter and the dashboard shows whether the team is getting better."], size=14, color=WHITE, fit=False)
    tb(s, 0.58, 6.50, 9.0, 0.40, [[("Code, spec and slides: ", True, NAVY), ("https://" + REPO, False, BLUE2), ("   MIT license", False, GREY)]], size=13, fit=False)
    tb(s, 0.58, 7.17, 5.80, 0.16, "Teaching lab for agent engineering and honest evaluation. Not investment advice.", size=6.8, color=MUTED, fit=False)
    tb(s, 11.98, 7.21, 0.80, 0.15, str(n), size=7.5, color=GREY, align=PP_ALIGN.RIGHT, fit=False); n += 1

    # B. the question
    s = base(prs, n, "The question we are asking", "A lab, not a product",
             "How well can an AI investment team trade, and does it get better with feedback?"); n += 1
    cards = [("Can it do quant research?", "Agents propose hypotheses, write strategy code, backtest it, and critique the result. Measured against buy-and-hold and a moving-average crossover."),
             ("Can it trade with judgment?", "A trader persona makes weekly BUY, SELL or HOLD calls from a point-in-time snapshot and must state its reason in one sentence."),
             ("Does coaching help?", "After each quarter a Review Agent studies the results and recommends changes. The next quarter shows whether they helped.")]
    for i, (t, bdy) in enumerate(cards):
        card(s, 0.55 + i*4.19, 1.92, 3.85, 2.05, i+1, t, bdy, body_size=13)
    light_banner(s, 0.55, 4.20, 12.23, 0.80, "Success is measured one way: the team's out-of-sample track record against SPY, season by season.", size=13)
    tb(s, 0.55, 5.25, 12.23, 1.0, ["SPY is the benchmark the team must beat. It never holds SPY.", "The team trades twelve large-cap US names: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO, AMD, CRM, ORCL, NFLX."], size=12, color=BODY, space_after=4)

    # C. assumptions
    s = base(prs, n, "Assumptions: free, local, and keyless", "Everything a student needs is a laptop and one download",
             footer="yfinance is an unofficial interface to Yahoo Finance; use it for personal and educational purposes and expect occasional gaps. Not investment advice."); n += 1
    stats = [("$0", "to run the whole lab, end to end"), ("0", "API keys, accounts or subscriptions"), ("13", "tickers: 12 traded, plus SPY as the benchmark"), ("16 GB", "of laptop RAM runs the default model")]
    for i, (big, small) in enumerate(stats):
        x = 0.55 + i*3.06
        rect(s, x, 1.10, 2.81, 1.30)
        tb(s, x+0.21, 1.22, 2.40, 0.50, big, size=24, bold=True, color=JHU, font=TITLE_FONT, fit=False)
        tb(s, x+0.21, 1.76, 2.40, 0.56, small, size=11.25, color=BODY)
    tb(s, 0.55, 2.62, 12.23, 0.25, "WHAT WE RELY ON", size=10.5, bold=True, color=BLUE2, fit=False)
    rel = [("Data: yfinance, daily bars", "Free, no key. Daily open, high, low, close and volume from 2015. Adjusted for splits and dividends. The Data Agent checks gaps and short histories and writes a report."),
           ("Model: Ollama with qwen3:8b", "Open weights under Apache 2.0, runs fully offline. Supports tool calling and JSON-schema output. Swap any Ollama model with one flag; qwen3:4b fits 8 GB laptops."),
           ("Compute: your own machine", "About 2 to 5 seconds per model call on Apple Silicon. A six-season campaign is roughly 300 calls, 20 to 30 minutes. Replay mode shows a recorded run in class."),
           ("Market model: deliberately simple", "US large caps, daily closes, long only, monthly desk rebalance (weekly is a coach lever), 5 basis points per unit of weight traded. No shorting, leverage, options or intraday data.")]
    for i, (t, bdy) in enumerate(rel):
        x = 0.55 + (i % 2) * 6.23; y = 2.95 + (i // 2) * 2.05
        card(s, x, y, 6.00, 1.90, i+1, t, bdy, num_fill=GREEN, body_size=12)

    # D. the team
    s = base(prs, n, "The team: seven roles and one orchestrator", "Each agent has one prompt file, one output schema, and at most four tools",
             "The model does the judgment. Plain Python does the arithmetic, the schedule and the bookkeeping."); n += 1
    team = [("Data Agent", "Turns a one-line brief into a checked, cached dataset with a manifest hash and a short report."),
            ("Idea Agent", "Reads the lab notebook and proposes distinct strategy hypotheses across families."),
            ("Coder Agent", "Writes generate_signals() for one hypothesis and fixes it when the sandbox objects."),
            ("Critic Agent", "Reads train and validation metrics and votes Keep or Discard, naming its concerns."),
            ("Trader personas", "Momentum, contrarian, risk-averse. Weekly calls from a snapshot with one sentence of reasoning."),
            ("PM Agent, optional", "Combines the three personas' votes into one allocation each week. The committee pattern."),
            ("Review Agent, the coach", "Studies each season and recommends changes, but only from a fixed menu of levers."),
            ("Orchestrator, plain code", "A state machine, not a model. Runs the phases in order and enforces every budget.")]
    for i, (t, bdy) in enumerate(team):
        x = 0.55 + (i % 4) * 3.1; y = 1.92 + (i // 4) * 2.12
        fill = JHU if i < 7 else GREEN
        card(s, x, y, 2.95, 1.95, i+1 if i < 7 else "py", t, bdy, num_fill=fill, title_size=12.5, body_size=12)
    light_banner(s, 0.55, 6.25, 12.23, 0.62, "Only the Data Agent uses tool calling. The other six get everything they need in the prompt, which is cheaper and more reliable for an 8B model.", size=11.5)

    # D2. the map, full width
    s = base(prs, n, "How it all fits together", "Agents do the judgment; plain Python does the schedule, the arithmetic and the bookkeeping",
             footer="docs/architecture.png in the repo, drawn by docs/draw_architecture.py. docs/ARCHITECTURE.md adds the agent table, the on-disk layout and where to change things."); n += 1
    picture(s, sh("architecture_parts.png"), 0.55, 1.05, 12.23, 6.05, valign="top")

    # E. how a season runs
    s = base(prs, n, "How a season runs", "One calendar quarter the team has never seen, traded once",
             "Research on the past, trade the sealed quarter, score it, get coached, repeat."); n += 1
    steps = [("Research", "Idea, Coder and Critic loop over hypotheses using only data from before the quarter."),
             ("Select", "Code, not a model, picks the best validation Sharpe under a turnover cap. That is the quant book."),
             ("Trade", "The quant book trades mechanically. The desk persona makes a discretionary call per stock at each rebalance."),
             ("Score", "Quant book, desk, team (half each), SPY and baselines. The track record grows by one quarter."),
             ("Review", "The coach reads the season packet and writes an assessment with 1 to 3 recommendations."),
             ("Apply", "Levers are applied automatically, or wait for you to click Accept. The next season begins.")]
    w = 1.90; gap = 0.165
    for i, (t, bdy) in enumerate(steps):
        x = 0.55 + i*(w+gap)
        rect(s, x, 1.95, w, 2.55)
        oval(s, x+0.14, 2.12, 0.38, str(i+1))
        tb(s, x+0.60, 2.13, w-0.70, 0.36, t, size=14, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
        tb(s, x+0.14, 2.65, w-0.28, 1.75, bdy, size=11.5)
        if i < 5: connector(s, x+w, 3.2, x+w+gap, 3.2)
    light_banner(s, 0.55, 4.75, 12.23, 0.62, "Default campaign: 6 seasons from 2025 Q1 to 2026 Q2, about 300 model calls, 20 to 30 minutes on a laptop.", size=12.5)
    tb(s, 0.55, 5.60, 12.23, 0.9, ["Season 1 also runs the Data Agent and a second research round. Later seasons reuse the cached data and carry the notebook forward.",
                                   "Budgets, not patience, end every loop: calls per season, minutes per season, strategies per round."], size=11.5, space_after=3)

    # F. seasons / walk-forward
    s = base(prs, n, "Why seasons: walk-forward testing stops the loop from peeking", "A fixed test set would be burned the first time the coach saw it",
             "Each quarter is traded exactly once, out of sample. Only then does it become history the team may learn from."); n += 1
    # timeline diagram
    x0, xw = 0.55, 7.6
    def bar(y, a, b, fill, label, color=WHITE):
        r = rect(s, x0 + a*xw, y, (b-a)*xw, 0.42, fill=fill, line=None, radius=0.03); shape_text(r, label, 9.5, True, color)
    years = ["2015", "", "", "", "", "2020", "", "", "", "", "2025", "2026"]
    for i, yr in enumerate(years):
        if yr: tb(s, x0 + i/12*xw - 0.2, 1.92, 0.5, 0.2, yr, size=8, color=GREY, align=PP_ALIGN.CENTER, fit=False)
    rows = [("Season 1, 2025 Q1", 0.00, 0.75, 0.75, 0.833, 0.833, 0.854),
            ("Season 2, 2025 Q2", 0.00, 0.771, 0.771, 0.854, 0.854, 0.875),
            ("Season 3, 2025 Q3", 0.00, 0.792, 0.792, 0.875, 0.875, 0.896)]
    for i, (lbl, a1, b1, a2, b2, a3, b3) in enumerate(rows):
        y = 2.22 + i*0.62
        tb(s, x0 + xw + 0.15, y+0.08, 1.6, 0.3, lbl, size=10, bold=True, color=NAVY, fit=False)
        bar(y, a1, b1, LIGHT, "Train", color=BODY); bar(y, a2, b2, BLUE2, "Val"); bar(y, a3, b3, NAVY, "")
    tb(s, x0, 4.15, xw, 0.3, "Navy block: the sealed quarter. It moves one step right each season.", size=10, color=GREY, fit=False)
    cols = [("Train", "2015 up to twelve months before the season. Every backtest runs here. The Idea, Coder and Critic agents see only this and the validation year."),
            ("Validation", "The twelve months before the season. The Critic judges here, and the selector picks the quant book here. Nothing from the season influences the choice."),
            ("Season", "The next quarter. Sealed until traded, scored once, then handed to the coach as history. The next season starts a quarter later.")]
    for i, (t, bdy) in enumerate(cols):
        x = 0.55 + i*4.19
        label_card(s, x, 4.55, 3.85, 1.55, t.upper(), bdy, body_size=11.5)
    light_banner(s, 0.55, 6.30, 12.23, 0.62, "What to watch: did validation Sharpe predict season Sharpe? With six seasons noise dominates. The lab teaches the measurement, not a guarantee.", size=11.5)

    # ---------- agent slides ----------
    def agent_slide(title, subtitle, callout, role, inp, out, tools, prompt, code, code_label="Code running"):
        nonlocal n
        s = base(prs, n, title, subtitle, callout); n += 1
        L = 0.55; LW = 4.55; y = 1.92
        for lbl, txt, h in (("ROLE", role, 1.05), ("INPUT", inp, 1.25), ("OUTPUT", out, 1.15), ("TOOLS AND LIMITS", tools, 1.05)):
            label_card(s, L, y, LW, h, lbl, txt, body_size=11); y += h + 0.12
        R = 5.30; RW = 7.48
        code_box(s, R, 1.92, RW, 2.30, prompt, label="Prompt, excerpt", size=10.5)
        code_box(s, R, 4.34, RW, 2.58, code, label=code_label, size=9.5)
        return s

    agent_slide("Data Agent", "Phase 0. Runs once per campaign; later seasons reuse the cache",
        "Lesson one: do not use a model where a function will do. The fetch is code; the judgment around it is the agent.",
        "Turn a plain-English brief into a validated, cached dataset and a short written report.",
        "A brief such as \"12 large-cap US tech names plus SPY, 2015 to today\", plus a bundled list of candidate tickers. No web search.",
        "data/raw/*.parquet, data/features/*.parquet, manifest.json with a SHA-256 of the prices, and REPORT.md in plain English.",
        "propose_tickers, fetch_prices, check_quality, replace_ticker. At most 12 tool calls. The only agent that uses tool calling.",
        "You assemble datasets for a long-only equity lab.\nTurn the brief into a ticker list with propose_tickers, fetch with\nfetch_prices, then read check_quality. Replace any name with under\n8 years of history or unexplained gaps. Finish with a short report:\nwhat was fetched, what you changed, and why. Never invent tickers;\nonly use names the tools return.",
        "plan = llm.structured(DATA_PROMPT, brief, schema=DataPlan)\n# -> tickers=[AAPL, MSFT, NVDA, ...], benchmark=\"SPY\"\n\nprices = fetch_prices(plan.tickers + [plan.benchmark],\n                      start=\"2015-01-01\")     # yfinance, parquet cache\nreport = check_quality(prices)                # gaps, NaNs, zero volume\nmanifest.write(prices, notes=plan.rationale)  # sha256 -> 3f9c...\n\n# the tool loop underneath (aitrader/agent.py)\nfor step in range(max_steps):\n    reply = ollama.chat(model, messages, tools=schemas(tools))\n    if not reply.message.tool_calls: return reply.message.content\n    for call in reply.message.tool_calls:\n        messages.append(tool_result(tools[call.function.name](**call.function.arguments)))")

    agent_slide("Idea Agent", "Phase 1. One call per research round, no tools",
        "Everything it needs is in the prompt: a 40-line feature catalog and one line per strategy already tried.",
        "Propose K distinct hypotheses across families: trend, mean reversion, volatility, cross-sectional momentum.",
        "The feature catalog, the lab notebook summary, the family focus set by the coach, and its own lessons.",
        "A list of Hypothesis objects: name, family, idea, features_used, why_it_might_work. JSON enforced by schema.",
        "No tools, temperature 0. For an 8B model, putting the information in the prompt is more reliable than letting it fetch.",
        "You are the research lead of a small quant team. Propose {K} distinct\nstrategy hypotheses using only the features listed. Do not repeat or\nlightly vary anything in the notebook. Cover different families.\nFocus: {family_focus}. Each idea must be testable as a daily, long-only\nweighting rule. Answer in the JSON schema provided.",
        "hyps = llm.structured(\n    system=prompts.load(\"idea\", lessons=store.lessons(\"idea\")),\n    user=f\"Features:\\n{features.catalog()}\\n\\nNotebook:\\n{notebook.summary()}\",\n    schema=list[Hypothesis],\n    temperature=0,\n)\n\n# under the hood, one Ollama call with schema-constrained output\nollama.chat(model=\"qwen3:8b\", messages=[...],\n            format=Hypothesis.schema(), options={\"temperature\": 0})\n\n# a Hypothesis, as returned\n{\"name\": \"breakout_20d_volscale\", \"family\": \"trend\",\n \"idea\": \"Buy closes above the prior 20-day high; hold while above sma20\",\n \"features_used\": [\"close\", \"ret_1d\"]}")

    agent_slide("Coder Agent", "Phase 1. One function per hypothesis, at most three attempts",
        "Every strategy, written by a person or a model, implements the same one-function interface.",
        "Translate one hypothesis into generate_signals() and repair it when the sandbox or the lookahead guard rejects it.",
        "One Hypothesis. On a retry, the exact error text and line number from the sandbox or the backtester.",
        "StrategyCode: the function body and a note. Weights between 0 and 1, one row per date, one column per ticker.",
        "No tools. Three attempts, then the hypothesis is marked failed in the notebook and the loop moves on.",
        "Write the body of generate_signals(prices, features) in pandas.\nUse only past data at each row. No imports, no file or network\naccess, no shift with a negative number. Return weights between 0\nand 1 for every ticker and date. Keep it under 40 lines and comment\neach indicator. If you receive an error, fix only what it names.",
        "def generate_signals(prices: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:\n    \"\"\"Target weights in [0, 1], indexed like prices. Past data only.\"\"\"\n    high20 = prices.rolling(20).max().shift(1)      # yesterday's 20-day high\n    sma20  = prices.rolling(20).mean()\n    entry  = prices > high20                        # breakout\n    exit_  = prices < sma20                         # trend lost\n    held   = entry.where(entry | exit_).ffill().fillna(False)\n    vol20  = features[\"ret_1d\"].rolling(20).std() * 252 ** 0.5\n    raw    = held.astype(float) / vol20             # inverse-vol sizing\n    w      = raw.div(raw.sum(axis=1), axis=0).fillna(0.0)\n    return w.clip(upper=0.30)                       # no name above 30%",
        code_label="What it wrote: breakout_20d_volscale")

    agent_slide("Critic Agent", "Phase 1. Reads numbers, not prices, and never sees the season",
        "Keep or Discard, with the concern named: overfitting, turnover, concentration.",
        "Review each backtested strategy on its train and validation metrics; flag overfitting and churn; suggest what to try next.",
        "The code, train metrics, validation metrics, the notebook summary, and lessons from the coach such as the turnover limit.",
        "Review: verdict KEEP or DISCARD, a list of concerns, and one suggestion. Written to the notebook with the metrics.",
        "No tools. The season window is still sealed when it runs, so it cannot grade on the answer.",
        "You are a skeptical risk reviewer. Compare train and validation\nSharpe: a gap above 0.5 suggests overfitting. Discard validation\nturnover above {max_turnover} percent per year. Flag any single-name\nweight above 30 percent. Say what evidence would change your mind.\nLessons from the coach: {lessons}",
        "review = llm.structured(\n    system=prompts.load(\"critic\", lessons=store.lessons(\"critic\")),\n    user=f\"Code:\\n{code}\\n\\nTrain: {m_train}\\nValidation: {m_val}\\n\\n\"\n         f\"Notebook:\\n{notebook.summary()}\",\n    schema=Review,              # verdict, concerns[], suggestion\n)\nnotebook.add(hyp, code, m_train, m_val, review)\n\n# a Review, as returned\n{\"verdict\": \"KEEP\",\n \"concerns\": [\"top position averages 28% of the book\"],\n \"suggestion\": \"test a 25% cap; turnover 140%/yr is inside the limit\"}")

    agent_slide("Trader personas, and the optional PM", "Phase 2. One call per ticker at each rebalance, from a point-in-time snapshot",
        "The persona sees only what existed on the decision date, about 300 tokens, and answers in a fixed JSON shape.",
        "Make a discretionary BUY, SELL or HOLD call with a target weight, a confidence, and one sentence grounded in the snapshot.",
        "Snapshot: last 20 closes, price against the 20, 50 and 200-day averages, RSI 14, returns over 1, 3 and 12 months, realized volatility, current weight.",
        "Decision: action, target_weight, confidence, reason. The engine fills at the next open and charges the cost.",
        "No tools. Three personas share the code and differ only by prompt file. With --committee a PM Agent merges their votes into one allocation.",
        "You are a momentum trader managing one sleeve of a long-only\nportfolio. ... Decide one action: BUY, SELL or HOLD, with a target\nweight between 0 and the maximum allowed, a confidence from 0 to 1,\nand one sentence grounded in the numbers shown. Never reference\ninformation not in the snapshot.\n## Lessons from the coach\n1. (after S1) Do not call a stock oversold unless RSI 14 is below 30\n   and it sits below its 50-day average.",
        "# what the model saw (features.snapshot(\"AAPL\", as_of=\"2025-10-20\"))\nticker: AAPL   as_of: 2025-10-20\ncloses_20d: 227.1 229.4 ... 236.8\nvs_sma20: +1.9%  vs_sma50: +4.2%  vs_sma200: +9.8%   rsi14: 58\nret_1m: +3.1%  ret_3m: +11.0%  ret_12m: +19.4%   vol_20d_ann: 21%\ncurrent_weight: 0.20   max_weight: 0.30\n\n# what it returned (schema-constrained, temperature 0)\n{\"action\": \"BUY\", \"target_weight\": 0.25, \"confidence\": 0.66,\n \"reason\": \"Broke above the 20-day high on rising volume; 3-month +11%; RSI 58.\"}\n\nengine.queue(\"AAPL\", 0.25, fill=\"next_open\")   # filled 21 Oct, cost 0.6 bp",
        code_label="One decision, in full")

    agent_slide("Review Agent, the coach", "Phase 4. One call per season. The only agent allowed to change the team",
        "It may recommend, but only from a fixed menu of levers, and every change is logged with a condition for reverting it.",
        "Assess the season in plain words, say what worked and what failed, and recommend one to three changes grounded in numbers.",
        "The season scorecard, the track record, the changelog, the notebook summary, and the desk's three best and three worst decisions. About 1,500 tokens.",
        "SeasonReview: assessment, what_worked, what_failed, recommendations, each with lever, target, change, rationale, expected_effect, revert_if.",
        "No tools. Levers: add_lesson, remove_lesson, set_param within a range, set_family_focus, retire_strategy, reinstate_strategy, revert. Universe, costs, data and model are frozen.",
        "You coach an AI investment team. Read the season packet. Explain the\nresult in plain words, grounded in the numbers. Recommend at most\nthree changes, each using one lever from the menu, with the metric\nyou expect to move and the condition for reverting it. Prefer\nremoving a bad lesson over adding a new one. Never touch the\nuniverse, costs, data or model.",
        "review = llm.structured(system=prompts.load(\"review\"),\n                        user=packet.as_text(), schema=SeasonReview)\nfor rec in review.recommendations:\n    change = LEVERS[rec.lever].apply(rec)   # raises if outside menu or range\n    changelog.append(change, season=s)\n\n# one recommendation, as returned\n{\"lever\": \"add_lesson\", \"target\": \"trader_momentum\",\n \"change\": \"After a drawdown over 8% reverses above the 20-day for two\n            weeks, re-enter rather than wait for the 50-day.\",\n \"rationale\": \"Waiting for the 50-day cost 7.1 points on SPY in April.\",\n \"expected_effect\": \"earlier re-entry\", \"revert_if\": \"two losing re-entries\"}",
        code_label="Apply, then the lesson appears in the prompt file")

    # M. deterministic core
    s = base(prs, n, "The deterministic core never calls the model", "Engine, sandbox, lookahead guard, selector, scorer: plain Python you can unit-test",
             "If it can be a function, it is a function. The model only fills the gaps that need judgment."); n += 1
    code_box(s, 0.55, 1.92, 4.0, 3.35, "def run(weights, prices, cost_bps=5):\n    w = weights.clip(0, 1).shift(1)   # lag 1 bar\n    w = w.fillna(0)\n    ret = prices.pct_change().fillna(0)\n    turn = w.diff().abs().sum(axis=1)\n    cost = cost_bps / 1e4 * turn\n    pnl = (w * ret).sum(axis=1) - cost\n    equity = (1 + pnl).cumprod()\n    return Result(equity, pnl, turn.sum())\n\n# per window: CAGR, vol, Sharpe,\n# Sortino, max drawdown, turnover, hit rate", label="Engine: tonight's signal trades tomorrow", size=9)
    code_box(s, 4.67, 1.92, 4.0, 3.35, "tree = ast.parse(code)\nfor node in ast.walk(tree):\n    if is_import(node):\n        raise Rejected(\"no imports\")\n    if is_call(node, \"shift\") and neg_arg(node):\n        raise Rejected(\n          f\"shift(-n) reads the future, \"\n          f\"line {node.lineno}\")\n    if is_call(node, (\"open\", \"eval\", \"exec\")):\n        raise Rejected(\"no files, no eval\")\nfn = run_in_subprocess(code, timeout=5)\n# allowed: pandas, numpy, math", label="Sandbox: model code never runs as-is", size=9)
    code_box(s, 8.79, 1.92, 3.99, 3.35, "full = fn(prices, features)\ncut  = fn(prices.iloc[:-60],\n          features.iloc[:-60])\nassert full.iloc[:-60].equals(cut)\n\n# selector: validation only\nbook = max((s for s in notebook.kept()\n            if s.val.sharpe >= 0.5\n            and s.val.turnover <= 300),\n           key=lambda s: s.val.sharpe)\n\n# scorer: half book, half desk\nteam = 0.5 * book.pnl + 0.5 * desk.pnl", label="Lookahead guard, selector, scorer", size=9)
    tb(s, 0.55, 5.45, 12.23, 0.25, "WHAT THE TESTS PROVE", size=10.5, bold=True, color=BLUE2, fit=False)
    tests = [("Engine", "A five-bar example worked by hand gives the exact equity curve, including the one-bar lag and the cost."),
             ("Sandbox", "Must reject import os, open(), and shift(-1), and must time out an infinite loop at five seconds."),
             ("Lookahead guard", "Must catch a strategy that deliberately peeks, and must pass every baseline.")]
    for i, (t, bdy) in enumerate(tests):
        x = 0.55 + i*4.19
        rect(s, x, 5.78, 3.85, 1.12)
        tb(s, x+0.16, 5.86, 3.5, 0.3, t, size=12, bold=True, color=NAVY, fit=False)
        tb(s, x+0.16, 6.16, 3.55, 0.70, bdy, size=10.5)

    # N. strategy in pictures
    s = base(prs, n, "A strategy the Coder wrote, shown on one ticker", "Price, indicators, entries, exits and position size, straight from the dashboard's Strategy tab",
             footer="Strategy tab of the live page. The chart is drawn from the book's actual weights and the cached prices."); n += 1
    picture(s, sh("strategy_chart.png"), 0.55, 1.10, 8.40, 4.30, valign="top")
    light_banner(s, 0.55, 5.60, 8.40, 1.30, "What the tab shows: the season's quant book on one ticker. In this run the equal-weight baseline won validation every season, so the book held each of the 12 names at 8%, rebalanced weekly. Cost: 5 bp per unit of weight traded. Fill: next open, never the same close.", size=11.5)
    cards = [("Read the chart", "Black is the close; blue and orange are the 20 and 50-day averages; grey steps are the previous 20-day high. Green triangles mark where the book entered, red where it exited. Shaded bands are days it held the name."),
             ("Below the price", "The weight the book assigned to this name, then the sleeve's growth against simply holding the stock at the book's maximum weight."),
             ("Why it matters in class", "Whatever the code says, students can check it against prices day by day, switch tickers, and open the trade list to see each entry and exit.")]
    for i, (t, bdy) in enumerate(cards):
        label_card(s, 9.15, 1.10 + i*1.98, 3.63, 1.84, t.upper(), bdy, body_size=10.5)

    # O. swarm rules
    s = base(prs, n, "Eight rules that keep a swarm in hand", "Enforced in code, not by convention",
             "A swarm here means separation of concerns, not a free-for-all. On one laptop it is not even faster."); n += 1
    rules = [("Fixed roster", "Seven roles, declared in code. No agent can spawn another agent."),
             ("The orchestrator is code", "A Python state machine runs the phases in order. No model decides who speaks next."),
             ("No agent-to-agent chat", "Agents read and write typed pydantic artifacts on a shared run store. No conversation loops."),
             ("One prompt, one schema", "Per agent: one prompt file, one output schema, at most four tools, at most three retries."),
             ("Budgets everywhere", "Calls, minutes and strategies per season and per campaign. Hitting a budget stops cleanly with partial results."),
             ("Sequential by default", "One laptop serves one model. A --parallel flag exists to prove that it buys nothing."),
             ("Everything replayable", "Every event is appended to a JSONL trace. The dashboard replays any run at 1x, 5x or instant."),
             ("The coach has a menu", "The Review Agent can only pull fixed levers inside allowed ranges. Universe, costs, data and model stay frozen.")]
    for i, (t, bdy) in enumerate(rules):
        x = 0.55 + (i % 4) * 3.1; y = 1.92 + (i // 4) * 2.08
        card(s, x, y, 2.95, 1.90, i+1, t, bdy, title_size=12.5, body_size=12)
    light_banner(s, 0.55, 6.15, 12.23, 0.72, "Budget math on a laptop: about 50 model calls and 4 minutes per season, so 6 seasons take 20 to 30 minutes. Three personas triple the desk calls, which is why Replay exists.", size=11.5)

    # P. Mission Control
    s = base(prs, n, "Mission Control: the dashboard students run in the browser", "One local page, no login. Press Walkthrough for the 17-step guided tour",
             footer="Live page during a real campaign on Oct 23, 2026, qwen3:8b on a Mac Studio."); n += 1
    picture(s, sh("walk.png"), 0.55, 1.10, 8.40, 4.80)
    feats = [("Walkthrough", "17 steps. Each Next reveals the agent events for that stage, highlights the panel, and shows the Python running at that moment plus the background processes."),
             ("Live feed and Step mode", "Every agent turn, tool call, decision and reason, colour-coded by agent. Pause and step one turn at a time while you narrate."),
             ("Tabs for everything", "Progress, Strategy, Season, Notebook, Desk, Reviews, Changelog, Prompts, Processes, Runs. Deep links such as #reviews jump straight there.")]
    for i, (t, bdy) in enumerate(feats):
        label_card(s, 9.15, 1.10 + i*1.62, 3.63, 1.50, t.upper(), bdy, body_size=10.5)
    light_banner(s, 0.55, 6.10, 12.23, 0.70, "Served by FastAPI with Server-Sent Events; one static HTML file, no build step, works offline. Start with: uv run python -m aitrader serve", size=11.5)

    # Q. Progress
    s = base(prs, n, "Is the team improving? The Progress tab", "Track record, excess return by season, and whether validation predicted the season",
             footer="Real run, Oct 23, 2026. A handful of seasons cannot separate skill from luck. The lab teaches the measurement and the honest question, not a result."); n += 1
    picture(s, sh("progress.png"), 0.55, 1.10, 8.40, 4.75)
    feats = [("Track record", "Growth of 1.00 across seasons the team had not seen, for team, quant book, desk and SPY. Numbered flags mark where each coach change took effect."),
             ("Did validation predict the season?", "Hollow dot: Sharpe on the validation year. Filled dot: Sharpe on the quarter it then traded. The gap is the overfitting lesson."),
             ("The cleanest test", "Run the same seasons with the coach switched off and overlay the two campaigns. The Runs tab does this with one click.")]
    for i, (t, bdy) in enumerate(feats):
        label_card(s, 9.15, 1.10 + i*1.62, 3.63, 1.50, t.upper(), bdy, body_size=10.5)
    light_banner(s, 0.55, 6.05, 12.23, 0.75, "Scorecard: seasons beating SPY, excess return since season 1, out-of-sample Sharpe, worst drawdown, strategies tried, lessons the coach kept.", size=11.5)

    # R. practices
    s = base(prs, n, "Agent engineering practices you can point to in the code", "Each one is named in a comment and in the README",
             "The repo is as much about how to build agents as about trading."); n += 1
    practices = [("Tools compute, the model reasons", "The model never does arithmetic or touches a DataFrame."),
                 ("Small, typed tools", "At most four per agent, documented, returning compact text."),
                 ("Schema-enforced outputs", "JSON shape fixed by the model's schema mode, validated by pydantic, retried with the error."),
                 ("Bounded loops", "Max steps, wall-clock budget, tool-call cap, call budget per season."),
                 ("Observability", "Every prompt, call and decision in a JSONL trace; replayable in the dashboard."),
                 ("No lookahead by construction", "Data sliced as-of the cutoff, one-bar execution lag, perturbation test."),
                 ("Sandboxed code", "AST allowlist, no imports or files, subprocess with a time limit."),
                 ("Evaluation first", "Train, validation, sealed season. Strategies tried are counted and shown."),
                 ("Reproducibility", "Temperature 0, pinned model tag, dataset hash, prompts stored with results."),
                 ("Memory", "A lab notebook and per-agent lessons persist across seasons."),
                 ("Human in the loop", "Step mode, approve mode for coach changes, editable prompts."),
                 ("Workflows over free-form agents", "The orchestrator is code; agents do judgment inside fixed phases.")]
    for i, (t, bdy) in enumerate(practices):
        x = 0.55 + (i % 3) * 4.19; y = 1.92 + (i // 3) * 1.25
        rect(s, x, y, 3.85, 1.12)
        oval(s, x+0.16, y+0.16, 0.26, str(i+1), fill=GREEN, size=8)
        tb(s, x+0.52, y+0.10, 3.20, 0.36, t, size=12, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
        tb(s, x+0.16, y+0.50, 3.55, 0.58, bdy, size=10.5)

    # R2. the first real run, if a run folder was given
    if RUN_DIR and (Path(RUN_DIR) / "track_record.json").exists():
        tr = json.loads((Path(RUN_DIR) / "track_record.json").read_text())
        meta = json.loads((Path(RUN_DIR) / "campaign.json").read_text()) if (Path(RUN_DIR) / "campaign.json").exists() else {}
        nb = [json.loads(l) for l in (Path(RUN_DIR) / "notebook.jsonl").read_text().splitlines() if l.strip()] if (Path(RUN_DIR) / "notebook.jsonl").exists() else []
        cl = [json.loads(l) for l in (Path(RUN_DIR) / "changelog.jsonl").read_text().splitlines() if l.strip()] if (Path(RUN_DIR) / "changelog.jsonl").exists() else []
        cum = lambda k: (eval("*".join(str(1 + (r.get(k) or 0)) for r in tr)) - 1) if tr else 0
        beat = sum(1 for r in tr if (r.get("team") or 0) > (r.get("spy") or 0))
        s = base(prs, n, "What actually happened: the first full run", f"{len(tr)} quarterly seasons, {meta.get('model', 'qwen3:8b')}, one momentum persona, coach on, Oct 23, 2026",
                 "Out of sample, season by season. Read it as a measurement of the loop, not as a verdict on AI trading.",
                 footer="Research tried " + str(len(nb)) + " strategies; the coach applied " + str(len([c for c in cl if c.get('status') != 'rejected'])) + " changes. Costs 5 bp per unit of weight traded. Partial seasons use data up to the last available day."); n += 1
        stats = [(f"{beat} of {len(tr)}", "seasons the team beat SPY"), (pct(cum("team") * 100), "team, compounded over the run"), (pct(cum("spy") * 100), "SPY over the same quarters"),
                 (pct(cum("book") * 100), "quant book alone"), ]
        for i, (big, small) in enumerate(stats):
            x = 0.55 + i * 3.06
            rect(s, x, 1.92, 2.81, 1.30)
            tb(s, x + 0.21, 2.04, 2.40, 0.50, big, size=24, bold=True, color=JHU, font=TITLE_FONT, fit=False)
            tb(s, x + 0.21, 2.58, 2.40, 0.56, small, size=11.25, color=BODY)
        cols = [("Season", 1.6), ("Quant book", 2.6), ("Val Sharpe", 1.1), ("Season Sharpe", 1.3), ("Team", 1.0), ("SPY", 1.0), ("Excess", 1.0), ("Desk", 1.0), ("Changes after", 1.6)]
        y = 3.50
        x = 0.55
        for name, w in cols:
            tb(s, x, y, w, 0.3, name, size=10.5, bold=True, color=GREY, fit=False, align=PP_ALIGN.RIGHT if name not in ("Season", "Quant book", "Changes after") else None)
            x += w
        y += 0.34
        for r in tr:
            x = 0.55
            vals = [f"S{r['season']}, {r.get('label', '')}" + (" (partial)" if r.get("partial") else ""), str(r.get("book_name") or ""),
                    "–" if r.get("book_val_sharpe") is None else f"{r['book_val_sharpe']:.2f}", "–" if r.get("book_season_sharpe") is None else f"{r['book_season_sharpe']:.2f}",
                    pct((r.get("team") or 0) * 100), pct((r.get("spy") or 0) * 100), pct(((r.get("team") or 0) - (r.get("spy") or 0)) * 100),
                    pct((r.get("desk") or 0) * 100), ", ".join(str(c["id"]) for c in cl if c.get("season") == r["season"]) or "–"]
            for (name, w), v in zip(cols, vals):
                tb(s, x, y, w, 0.3, v, size=11, color=BODY, fit=False, align=PP_ALIGN.RIGHT if name not in ("Season", "Quant book", "Changes after") else None)
                x += w
            y += 0.32
        light_banner(s, 0.55, max(y + 0.15, 5.9), 12.23, 0.70, "Questions for the room: did validation Sharpe predict the season? Did the coach's changes do what they expected? Would a run with the coach switched off look different?", size=11.5)

    # S. run it yourself
    s = base(prs, n, "Run it yourself", "Everything is public. Clone it, pull one model, open the page",
             footer="Published Oct 24, 2026: design spec, dashboard and the Python package are in the repo. 52 offline tests; verified end to end against Ollama with real data."); n += 1
    code_box(s, 0.55, 1.10, 7.3, 2.65, "ollama pull qwen3:8b\ngit clone https://" + REPO + ".git && cd aiInvesting\nuv run python -m aitrader serve          # http://localhost:8000, click Run campaign\n\n# or the command line\nuv run python -m aitrader campaign --quick               # 2 short seasons, ~2 min\nuv run python -m aitrader campaign --personas momentum,contrarian --apply approve\nuv run python -m aitrader replay runs/<campaign> --speed 5\nuv run pytest                                            # 52 offline tests", label="Three commands", size=9.5)
    rect(s, 8.05, 1.10, 4.73, 2.65)
    tb(s, 8.21, 1.20, 4.4, 0.24, "WHICH MODEL FOR WHICH LAPTOP", size=9.5, bold=True, color=BLUE2, fit=False)
    rows = [("8 GB", "qwen3:4b", "slower; run 3 seasons; use Replay in class"), ("16 GB", "qwen3:8b", "the default, verified"), ("32 GB+", "qwen3:14b", "better code, about twice as slow")]
    for i, (ram, model, note) in enumerate(rows):
        y = 1.52 + i*0.70
        tb(s, 8.21, y, 0.9, 0.3, ram, size=13, bold=True, color=JHU, font=TITLE_FONT, fit=False)
        tb(s, 9.15, y, 1.4, 0.3, model, size=11, bold=True, color=NAVY, font=MONO, fit=False)
        tb(s, 9.15, y+0.28, 3.5, 0.36, note, size=10, color=BODY)
    tb(s, 0.55, 4.00, 12.23, 0.25, "IN THE REPO", size=10.5, bold=True, color=BLUE2, fit=False)
    items = [("docs/superpowers/specs/", "The full design: roles, phases, schemas, lever menu, budgets, error handling, test plan, two-day build schedule."),
             ("docs/mockups/mission-control.html", "The dashboard you just saw. One file, open it in any browser, no server needed."),
             ("aitrader/", "The package: orchestrator, agents, prompts, levers, sandbox, engine, web server. 52 tests run offline with a fake model."),
             ("No secrets, by design", "Nothing in the repo needs a key, so there is nothing to leak. The .gitignore excludes data and run folders. MIT license.")]
    for i, (t, bdy) in enumerate(items):
        x = 0.55 + (i % 2) * 6.23; y = 4.35 + (i // 2) * 1.25
        rect(s, x, y, 6.0, 1.12)
        tb(s, x+0.16, y+0.10, 5.7, 0.30, t, size=12, bold=True, color=NAVY, font=MONO if "/" in t else BODY_FONT, fit=False)
        tb(s, x+0.16, y+0.44, 5.7, 0.62, bdy, size=10.5)
    tb(s, 0.55, 6.80, 12.23, 0.35, [[("https://" + REPO, True, BLUE2), ("   open source under the MIT license", False, GREY)]], size=14, fit=False)

    # T. questions
    s = base(prs, n, "Questions for the room", "Argue from the numbers the dashboard shows",
             "Six seasons of data, seven agents, one coach. What would convince you the team is skilled rather than lucky?"); n += 1
    qs = [("Did validation predict the season?", "Look at the hollow and filled dots. If a strategy's validation Sharpe does not predict its season Sharpe, what is the selector actually selecting?"),
          ("Would you let the coach apply changes automatically?", "Auto mode closes the loop. Approve mode makes you the risk committee. Which would a real fund choose, and why?"),
          ("Where could lookahead still sneak in?", "The engine lags one bar, the sandbox blocks negative shifts, the perturbation test withholds 60 days. What did we miss?"),
          ("Is a 50/50 team blend fair?", "The headline number is half quant book, half discretionary desk. Should the headline be whichever did better, or neither?")]
    for i, (t, bdy) in enumerate(qs):
        x = 0.55 + (i % 2) * 6.23; y = 1.92 + (i // 2) * 2.12
        card(s, x, y, 6.0, 1.95, i+1, t, bdy, body_size=13.5)
    light_banner(s, 0.55, 6.25, 12.23, 0.62, "Open the dashboard at any point. Every number on these slides is one click away in Mission Control.", size=12)
    return n

# ---------- build v1.2: template + section ----------
prs = Presentation(TEMPLATE)
start = len(prs.slides) + 1
build_section(prs, start)
prs.save(OUT_V12)
print("v1.2 saved:", OUT_V12, "slides:", len(prs.slides))

# ---------- standalone: template with original slides removed ----------
prs2 = Presentation(TEMPLATE)
sldIdLst = prs2.slides._sldIdLst
for sldId in list(sldIdLst):
    prs2.part.drop_rel(sldId.rId); sldIdLst.remove(sldId)
build_section(prs2, 1)
prs2.save(OUT_SOLO)
print("standalone saved:", OUT_SOLO, "slides:", len(prs2.slides))
