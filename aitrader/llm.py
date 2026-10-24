"""Thin wrapper over the Ollama client.

structured(): schema-constrained JSON, validated by pydantic, retried with the
error fed back (practice P3). chat_with_tools(): the bounded tool loop
(practice P4). Every call is counted against a Budget and emitted as an event.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from pydantic import BaseModel

from .agent import tool_schema
from .events import EventBus


class AgentError(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, max_llm_calls: int = 60, max_minutes: float = 15.0):
        self.max_llm_calls = int(max_llm_calls)
        self.max_minutes = float(max_minutes)
        self.reset()

    def reset(self) -> None:
        self.calls = 0
        self.started = time.time()

    @property
    def minutes(self) -> float:
        return (time.time() - self.started) / 60.0

    def spend(self) -> None:
        self.calls += 1
        if self.calls > self.max_llm_calls:
            raise BudgetExceeded(f"LLM call budget of {self.max_llm_calls} exceeded")
        if self.minutes > self.max_minutes:
            raise BudgetExceeded(f"time budget of {self.max_minutes:.0f} minutes exceeded")

    def to_dict(self) -> dict:
        return {"calls": self.calls, "max_calls": self.max_llm_calls, "minutes": round(self.minutes, 1),
                "max_minutes": self.max_minutes}


class LLM:
    def __init__(self, model: str = "qwen3:8b", bus: EventBus | None = None, budget: Budget | None = None,
                 host: str | None = None):
        import ollama  # local import keeps tests without Ollama importable

        self._ollama = ollama
        self.client = ollama.Client(host=host) if host else ollama.Client()
        self.model = model
        self.bus = bus
        self.budget = budget
        self.calls = 0
        self.total_ms = 0
        self._think_ok = True

    # ---- health ----
    def health(self) -> tuple[bool, str]:
        try:
            names = [m.model for m in self.client.list().models]
        except Exception as e:
            return False, f"Ollama is not reachable ({e}). Start it with: ollama serve"
        base = self.model.split(":")[0]
        if not any(n == self.model or n.split(":")[0] == base for n in names):
            return False, f"Model {self.model} is not pulled. Run: ollama pull {self.model}"
        return True, f"Ollama ok, {self.model} available"

    # ---- raw call ----
    def _chat(self, messages: list[dict], agent: str, fmt: Any = None, tools: list | None = None):
        if self.budget:
            self.budget.spend()
        self.calls += 1
        t0 = time.time()
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "options": {"temperature": 0}}
        if fmt is not None:
            kwargs["format"] = fmt
        if tools:
            kwargs["tools"] = tools
        if self._think_ok:
            kwargs["think"] = False
        try:
            resp = self.client.chat(**kwargs)
        except self._ollama.ResponseError as e:
            if "think" in str(e).lower() and self._think_ok:
                self._think_ok = False
                kwargs.pop("think", None)
                resp = self.client.chat(**kwargs)
            else:
                raise
        ms = int((time.time() - t0) * 1000)
        self.total_ms += ms
        if self.bus:
            self.bus.emit("llm_call", agent=agent, ms=ms, prompt_chars=sum(len(str(m.get("content", ""))) for m in messages),
                          tool_calls=len(resp.message.tool_calls or []) if tools else 0)
        return resp

    # ---- structured output ----
    def structured(self, system: str, user: str, schema: type[BaseModel], agent: str = "", retries: int = 3):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        fmt = schema.model_json_schema()
        last_err = ""
        for attempt in range(1, retries + 1):
            resp = self._chat(messages, agent, fmt=fmt)
            content = resp.message.content or ""
            try:
                return schema.model_validate_json(content)
            except Exception as e:
                last_err = str(e).splitlines()[0][:300]
                if self.bus:
                    self.bus.emit("llm_retry", agent=agent, attempt=attempt, error=last_err)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Your previous answer was invalid: {last_err}. "
                                                            f"Answer again with only the JSON object."})
        raise AgentError(f"{agent or 'agent'}: invalid output after {retries} attempts: {last_err}")

    # ---- tool loop ----
    def chat_with_tools(self, system: str, user: str, tools: dict[str, Callable], max_steps: int = 12,
                        agent: str = "") -> str:
        schemas = [tool_schema(fn, name) for name, fn in tools.items()]
        messages: list[Any] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for _ in range(max_steps):
            resp = self._chat(messages, agent, tools=schemas)
            msg = resp.message
            messages.append(msg)
            if not msg.tool_calls:
                return msg.content or ""
            for call in msg.tool_calls:
                name = call.function.name
                args = dict(call.function.arguments or {})
                fn = tools.get(name)
                try:
                    result = fn(**args) if fn else f"unknown tool {name}"
                except TypeError as e:
                    result = f"error calling {name}: {e}"
                except Exception as e:  # tool failures go back to the model as text
                    result = f"error: {type(e).__name__}: {e}"
                if self.bus:
                    self.bus.emit("tool_call", agent=agent, tool=name, args=args, result=str(result)[:600])
                messages.append({"role": "tool", "content": str(result), "tool_name": name})
        raise AgentError(f"{agent or 'agent'}: exceeded {max_steps} tool steps")
