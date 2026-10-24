"""Event bus and JSONL trace.

Practice P5 (observability): every prompt, tool call, decision and score is an
Event. Events go to subscribers (the web server's SSE clients) and are appended
to runs/<campaign>/trace.jsonl. Replay reads the same shape the live page gets.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass
class Event:
    ts: str
    seq: int
    campaign: str | None
    season: int | None
    phase: str | None
    agent: str | None
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, line: str) -> "Event":
        d = json.loads(line)
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


class EventBus:
    """Thread-safe emitter. Context (campaign, season, phase, agent) is stamped on every event."""

    def __init__(self, trace_path: str | Path | None = None):
        self.trace_path = Path(trace_path) if trace_path else None
        self._subs: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        self.seq = 0
        self.campaign: str | None = None
        self.season: int | None = None
        self.phase: str | None = None
        self.agent: str | None = None
        if self.trace_path:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            if self.trace_path.exists():
                with open(self.trace_path) as f:
                    self.seq = sum(1 for _ in f)

    def set_context(self, **kw: Any) -> None:
        for k, v in kw.items():
            if k not in ("campaign", "season", "phase", "agent"):
                raise KeyError(k)
            setattr(self, k, v)

    def subscribe(self, fn: Callable[[Event], None]) -> Callable[[Event], None]:
        self._subs.append(fn)
        return fn

    def unsubscribe(self, fn: Callable[[Event], None]) -> None:
        if fn in self._subs:
            self._subs.remove(fn)

    def emit(self, kind: str, **payload: Any) -> Event:
        with self._lock:
            self.seq += 1
            ev = Event(
                ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                seq=self.seq,
                campaign=self.campaign,
                season=self.season,
                phase=self.phase,
                agent=self.agent,
                kind=kind,
                payload=payload,
            )
            if self.trace_path:
                with open(self.trace_path, "a") as f:
                    f.write(ev.to_json() + "\n")
        for fn in list(self._subs):
            try:
                fn(ev)
            except Exception:  # a broken subscriber must never stop the run
                pass
        return ev


def read_trace(path: str | Path) -> list[Event]:
    out: list[Event] = []
    p = Path(path)
    if not p.exists():
        return out
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(Event.from_json(line))
    return out
