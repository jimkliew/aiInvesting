"""A stand-in for aitrader.llm.LLM so agent logic is testable without Ollama."""
from __future__ import annotations

import json
from typing import Any, Callable

from aitrader.llm import AgentError


class FakeLLM:
    def __init__(self, responses: list[Any] | None = None, default: Callable | None = None):
        self.responses = list(responses or [])
        self.default = default          # fallback: fn(schema, system, user) -> dict|str
        self.calls = 0
        self.log: list[dict] = []
        self.model = "fake"
        self.budget = None
        self.bus = None

    def health(self):
        return True, "fake llm"

    def _next(self, schema, system, user):
        if self.responses:
            r = self.responses.pop(0)
        elif self.default:
            r = self.default(schema, system, user)
        else:
            raise AgentError("FakeLLM has no response left")
        if callable(r):
            r = r(system, user)
        return r

    def structured(self, system, user, schema, agent="", retries=3, temperature=0.0):
        last = ""
        for _ in range(retries):
            self.calls += 1
            r = self._next(schema, system, user)
            self.log.append({"agent": agent, "system": system, "user": user, "response": r})
            try:
                if isinstance(r, str):
                    return schema.model_validate_json(r)
                return schema.model_validate(r)
            except Exception as e:
                last = str(e).splitlines()[0]
        raise AgentError(f"{agent}: invalid output after {retries} attempts: {last}")

    def chat_with_tools(self, system, user, tools, max_steps=12, agent=""):
        """Script: a list of ("tool", name, kwargs) steps ending with ("final", text)."""
        self.calls += 1
        script = self._next(None, system, user)
        transcript = []
        for step in script:
            if step[0] == "tool":
                _, name, kwargs = step
                try:
                    transcript.append(str(tools[name](**kwargs)))
                except Exception as e:  # mirror the real loop: tool errors go back as text
                    transcript.append(f"error: {type(e).__name__}: {e}")
            else:
                return step[1]
        return "\n".join(transcript)
