"""Sandbox for model-written strategy code (practice P7).

check_source(): AST allowlist. run_strategy(): executes in a subprocess with a
time limit and restricted builtins, exchanging data through parquet files.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

BANNED_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "input", "breakpoint", "exit", "quit", "help", "memoryview",
}


class Rejected(Exception):
    def __init__(self, reason: str, lineno: int | None = None):
        self.reason = reason
        self.lineno = lineno
        super().__init__(f"line {lineno}: {reason}" if lineno else reason)


def _negative_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return isinstance(node.operand.value, (int, float)) and node.operand.value > 0
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and node.value < 0


def check_source(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise Rejected(f"syntax error: {e.msg}", e.lineno)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise Rejected("imports are not allowed; pd and np are already available", node.lineno)
        if isinstance(node, ast.FunctionDef) and node.name == "generate_signals":
            found = True
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise Rejected(f"attribute {node.attr} is not allowed", node.lineno)
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            raise Rejected(f"{node.id} is not allowed", node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "shift":
            args = list(node.args) + [kw.value for kw in node.keywords if kw.arg in (None, "periods")]
            if any(_negative_literal(a) for a in args):
                raise Rejected("shift with a negative number reads the future", node.lineno)
    if not found:
        raise Rejected("code must define generate_signals(prices, features)")


def run_strategy(code: str, prices: pd.DataFrame, features: dict[str, pd.DataFrame], timeout: float = 20) -> pd.DataFrame:
    """Run generate_signals in a subprocess; return weights aligned to prices. Raises Rejected."""
    check_source(code)
    with tempfile.TemporaryDirectory(prefix="aitrader-sandbox-") as tmp:
        d = Path(tmp)
        prices.to_parquet(d / "prices.parquet")
        (d / "features").mkdir()
        for k, v in features.items():
            v.to_parquet(d / "features" / f"{k}.parquet")
        (d / "code.py").write_text(code)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "aitrader.backtest.sandbox_runner", str(d)],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise Rejected(f"strategy timed out after {timeout:.0f} s")
        if proc.returncode != 0:
            lines = [ln for ln in proc.stderr.strip().splitlines() if ln.strip()]
            exc = lines[-1].strip() if lines else "unknown error"
            loc = next((ln.strip() for ln in reversed(lines) if 'File "<strategy>"' in ln), "")
            raise Rejected(f"strategy raised {exc[:300]}" + (f" ({loc})" if loc else ""))
        w = pd.read_parquet(d / "weights.parquet")
    w = w.reindex(index=prices.index, columns=prices.columns).astype(float).fillna(0.0)
    return w
