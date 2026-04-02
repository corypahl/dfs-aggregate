from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_text(path: Path, text: str) -> None:
    ensure_directory(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text or text in {"-", "None", "null"}:
        return None

    text = text.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def compute_value(projection: float | None, salary: float | None) -> float | None:
    if projection is None or salary in (None, 0):
        return None
    return round((projection / salary) * 1000, 2)


def clean_name(name: str) -> str:
    text = name.strip()
    text = text.replace("''", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def combine_name(first_name: str | None, last_name: str | None) -> str:
    first = clean_name(first_name or "")
    last = clean_name(last_name or "")
    return clean_name(f"{first} {last}".strip())


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.lower())


def first_present(values: Iterable[Any]) -> Any:
    for value in values:
        if value not in (None, "", []):
            return value
    return None
