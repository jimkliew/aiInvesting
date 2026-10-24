import pytest
from pydantic import BaseModel

from aitrader.agent import tool, tool_schema
from aitrader.llm import AgentError, Budget, BudgetExceeded
from tests.fakes import FakeLLM


class Out(BaseModel):
    x: int
    tag: str = "t"


def test_structured_first_try():
    llm = FakeLLM(['{"x": 1}'])
    assert llm.structured("s", "u", Out, agent="a").x == 1 and llm.calls == 1


def test_structured_retries_then_succeeds():
    llm = FakeLLM(["not json", '{"x": "nope"}', '{"x": 3}'])
    assert llm.structured("s", "u", Out).x == 3 and llm.calls == 3


def test_structured_gives_up():
    llm = FakeLLM(["bad", "bad", "bad"])
    with pytest.raises(AgentError):
        llm.structured("s", "u", Out, agent="critic")


def test_budget():
    b = Budget(max_llm_calls=2, max_minutes=10)
    b.spend(); b.spend()
    with pytest.raises(BudgetExceeded):
        b.spend()
    assert b.to_dict()["calls"] == 3


def test_tool_schema_from_signature():
    @tool("Fetch prices for tickers")
    def fetch_prices(tickers: list[str], start: str, years: int = 8) -> str:
        return "ok"

    s = tool_schema(fetch_prices)
    f = s["function"]
    assert f["name"] == "fetch_prices" and f["description"].startswith("Fetch")
    assert f["parameters"]["properties"]["tickers"] == {"type": "array", "items": {"type": "string"}}
    assert f["parameters"]["required"] == ["tickers", "start"]


def test_fake_tool_loop():
    seen = {}

    def fetch_prices(tickers: list[str]) -> str:
        seen["t"] = tickers
        return "fetched 2"

    llm = FakeLLM([[("tool", "fetch_prices", {"tickers": ["A", "B"]}), ("final", "done")]])
    assert llm.chat_with_tools("s", "u", {"fetch_prices": fetch_prices}) == "done"
    assert seen["t"] == ["A", "B"]
