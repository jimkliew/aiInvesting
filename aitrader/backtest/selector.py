"""Selector: plain code picks the quant book on validation metrics only (practice P8)."""
from __future__ import annotations


def eligible(entry: dict, params) -> bool:
    val = entry.get("val") or {}
    sharpe = val.get("sharpe")
    if sharpe is None:
        return False
    turnover_pct = float(val.get("turnover", 0.0)) * 100.0
    return sharpe >= float(params["critic.min_val_sharpe"]) and turnover_pct <= float(params["selector.max_turnover"])


def select(candidates: list[dict], params, previous_book: dict | None) -> tuple[dict | None, bool]:
    """Return (book, fallback). book has name, code, val. fallback=True when nothing qualified."""
    ok = [e for e in candidates if eligible(e, params)]
    if ok:
        best = max(ok, key=lambda e: e["val"]["sharpe"])
        return best, False
    if previous_book and previous_book.get("name"):
        return previous_book, True
    return None, True
