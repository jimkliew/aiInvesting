"""Typed hand-offs between agents (practice P15).

Every agent reads and writes one of these. Ollama's schema mode constrains the
model's answer to the JSON schema of the output model; pydantic validates it.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Family = Literal["trend", "mean_reversion", "volatility", "cross_sectional"]


class Hypothesis(BaseModel):
    name: str = Field(description="snake_case identifier, e.g. breakout_20d_volscale")
    family: Family
    idea: str = Field(description="one or two sentences: the rule to test")
    features_used: list[str] = Field(default_factory=list)
    why_it_might_work: str = ""


class Hypotheses(BaseModel):
    items: list[Hypothesis]


class StrategyCode(BaseModel):
    code: str = Field(description="Python source that defines generate_signals(prices, features)")
    notes: str = ""


class Review(BaseModel):
    verdict: Literal["KEEP", "DISCARD"]
    concerns: list[str] = Field(default_factory=list)
    suggestion: str = ""


class Decision(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    target_weight: float = Field(description="0 to max_weight")
    confidence: float = Field(description="0 to 1")
    reason: str = Field(description="one sentence grounded in the snapshot")


Lever = Literal[
    "add_lesson",
    "remove_lesson",
    "set_param",
    "set_family_focus",
    "retire_strategy",
    "reinstate_strategy",
    "revert",
]


class Recommendation(BaseModel):
    lever: Lever
    target: str = Field(description="agent name, parameter name, strategy name, or change id")
    change: str = Field(description="lesson text, new value, family list, or empty")
    rationale: str
    expected_effect: str = ""
    revert_if: str = ""


class SeasonReview(BaseModel):
    assessment: str
    what_worked: str
    what_failed: str
    recommendations: list[Recommendation] = Field(default_factory=list)


class Metrics(BaseModel):
    total_return: float
    cagr: float
    vol: float
    sharpe: float
    sortino: float
    max_dd: float
    calmar: float
    turnover: float
    hit_rate: float
    n_days: int


class DataPlan(BaseModel):
    tickers: list[str]
    benchmark: str = "SPY"
    rationale: str = ""


class DataSummary(BaseModel):
    report: str
