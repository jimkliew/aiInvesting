"""Tool declarations for the tool loop (practice P2: small, typed, documented tools)."""
from __future__ import annotations

import inspect
import typing
from typing import Any, Callable

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _json_type(annotation: Any) -> dict:
    origin = typing.get_origin(annotation)
    if origin in (list, tuple):
        (inner,) = typing.get_args(annotation) or (str,)
        return {"type": "array", "items": _json_type(inner)}
    if annotation in _JSON_TYPES:
        return {"type": _JSON_TYPES[annotation]}
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}
    return {"type": "string"}


def tool(description: str):
    """Decorator: attach a description so tool_schema() can describe the function to the model."""

    def deco(fn: Callable) -> Callable:
        fn._tool_description = description  # type: ignore[attr-defined]
        return fn

    return deco


def tool_schema(fn: Callable, name: str | None = None) -> dict:
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn) if hasattr(fn, "__annotations__") else {}
    props, required = {}, []
    for pname, p in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        props[pname] = _json_type(hints.get(pname, p.annotation))
        if p.default is inspect.Parameter.empty:
            required.append(pname)
    desc = getattr(fn, "_tool_description", None) or (inspect.getdoc(fn) or "").split("\n")[0]
    return {
        "type": "function",
        "function": {
            "name": name or fn.__name__,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }
