from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any

from .config import PROJECT_ROOT
from .history import record_snapshot
from .plan_builder import build_logistics_payload
from .source_data import source_paths
from .utils import source_signature


CURRENT_FILE = PROJECT_ROOT / "data" / "processed" / "logistics_current.json"
_REFRESH_LOCK = threading.Lock()


def _read_current() -> dict[str, Any]:
    if not CURRENT_FILE.exists():
        return {}

    try:
        with open(CURRENT_FILE, "r", encoding="utf-8") as infile:
            return json.load(infile)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_current(payload: dict[str, Any]) -> None:
    CURRENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CURRENT_FILE.with_suffix(".json.tmp")

    with open(temporary, "w", encoding="utf-8") as outfile:
        json.dump(payload, outfile, indent=2, ensure_ascii=False)

    os.replace(temporary, CURRENT_FILE)


def refresh_logistics(force: bool = False) -> dict[str, Any]:
    with _REFRESH_LOCK:
        signature = source_signature(source_paths())
        current = _read_current()

        if (
            not force
            and current
            and current.get("source_signature") == signature
        ):
            return current

        payload = build_logistics_payload()
        payload["source_signature"] = signature

        run_id, history_written = record_snapshot(payload, signature)
        payload["history_run_id"] = run_id
        payload["history_written"] = history_written

        # Snapshot rows are retained in SQLite and do not need to be sent to browsers.
        payload.pop("snapshot_rows", None)
        _write_current(payload)
        return payload


def get_current_payload() -> dict[str, Any]:
    return refresh_logistics(force=False)
