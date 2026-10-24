import json

import pytest

from aitrader.agents.coder_agent import strip_fences, write_code
from aitrader.agents.critic_agent import fmt_metrics, review
from aitrader.agents.idea_agent import describe_focus, propose, slug
from aitrader.llm import AgentError
from aitrader.schemas import Hypothesis, Metrics
from tests.fakes import FakeLLM

HYPS = json.dumps({"items": [
    {"name": "Breakout 20d", "family": "trend", "idea": "buy breakouts", "features_used": ["high20"], "why_it_might_work": "momentum"},
    {"name": "breakout_20d", "family": "trend", "idea": "dup", "features_used": [], "why_it_might_work": ""},
    {"name": "rsi dip", "family": "mean_reversion", "idea": "buy dips", "features_used": ["rsi14"], "why_it_might_work": "overreaction"},
]})


def test_propose_dedupes_and_limits():
    llm = FakeLLM([HYPS])
    hyps = propose(llm, 2, "catalog", "(empty)", {"emphasise": ["trend"], "avoid": ["mean_reversion"]}, None)
    assert [h.name for h in hyps] == ["breakout_20d", "breakout_20d_v2"]
    assert "emphasise trend; avoid mean_reversion" in llm.log[0]["system"]
    assert "Lab notebook" in llm.log[0]["user"]


def test_slug_and_focus():
    assert slug("  My Great-Strategy!! ") == "my_great_strategy"
    assert describe_focus(None) == "no preference"


def test_write_code_strips_fences_and_passes_feedback():
    hyp = Hypothesis(name="x", family="trend", idea="do x", features_used=["sma20"])
    llm = FakeLLM([json.dumps({"code": "```python\ndef generate_signals(prices, features):\n    return prices\n```", "notes": "n"})])
    out = write_code(llm, hyp, "catalog", feedback="line 2: shift(-1) reads the future")
    assert out.code.startswith("def generate_signals") and "```" not in out.code
    assert "shift(-1)" in llm.log[0]["user"]
    assert strip_fences("```\nx\n```") == "x\n"


def test_review_parses_and_errors():
    m = Metrics(total_return=0.4, cagr=0.1, vol=0.2, sharpe=1.1, sortino=1.5, max_dd=-0.2, calmar=0.5,
                turnover=1.4, hit_rate=0.5, n_days=250)
    assert "Sharpe 1.10" in fmt_metrics(m) and "turnover 140%/yr" in fmt_metrics(m)
    llm = FakeLLM([json.dumps({"verdict": "DISCARD", "concerns": ["turnover"], "suggestion": "slower"})])
    r = review(llm, "code", m, m, "(empty)", None, 0.5, 300)
    assert r.verdict == "DISCARD" and "300" in llm.log[0]["system"]
    bad = FakeLLM(["nope", "nope", "nope"])
    with pytest.raises(AgentError):
        review(bad, "code", m, m, "(empty)", None, 0.5, 300)
