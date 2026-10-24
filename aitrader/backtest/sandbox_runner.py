"""Subprocess entry point for the sandbox. Do not import from the rest of the package."""
from __future__ import annotations

import builtins
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

_ALLOWED = [
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len", "list",
    "map", "max", "min", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip", "print",
    "True", "False", "None", "ValueError", "KeyError", "TypeError", "Exception",
]
SAFE_BUILTINS = {k: getattr(builtins, k) for k in _ALLOWED if hasattr(builtins, k)}


def main(d: Path) -> None:
    code = (d / "code.py").read_text()
    prices = pd.read_parquet(d / "prices.parquet")
    features = {p.stem: pd.read_parquet(p) for p in sorted((d / "features").glob("*.parquet"))}
    ns = {"pd": pd, "np": np, "__builtins__": SAFE_BUILTINS}
    exec(compile(code, "<strategy>", "exec"), ns)
    fn = ns.get("generate_signals")
    if fn is None:
        raise RuntimeError("generate_signals is not defined")
    w = fn(prices, features)
    if not isinstance(w, pd.DataFrame):
        raise TypeError(f"generate_signals must return a DataFrame, got {type(w).__name__}")
    w = w.reindex(index=prices.index, columns=prices.columns).astype(float).fillna(0.0)
    w.to_parquet(d / "weights.parquet")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
