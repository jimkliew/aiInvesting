"""Dataset manifest with a content hash (practice P9: reproducibility)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def prices_hash(prices: pd.DataFrame) -> str:
    return hashlib.sha256(prices.round(6).to_csv().encode()).hexdigest()


def write_manifest(prices: pd.DataFrame, path: str | Path = "data/manifest.json", notes: str = "") -> dict:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    m = {
        "tickers": list(prices.columns),
        "start": str(prices.index.min().date()),
        "end": str(prices.index.max().date()),
        "rows": int(len(prices)),
        "sha256": prices_hash(prices),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes": notes,
    }
    p.write_text(json.dumps(m, indent=2))
    return m


def read_manifest(path: str | Path = "data/manifest.json") -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None
