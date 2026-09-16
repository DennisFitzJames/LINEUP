from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import (
    AREAS_FILE,
    PROJECT_ROOT,
    SOURCES_FILE,
    first_existing,
    load_area_config,
    load_picker_names,
    load_sources_config,
)
from .tabular import pick_value, read_rows
from .utils import clean_text, normalise_order_number, to_float


CAPACITIES_FILE = PROJECT_ROOT / "data" / "processed" / "capacities_clean.csv"
PRODUCTION_FILE = PROJECT_ROOT / "data" / "processed" / "production_list_clean.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as infile:
        return list(csv.DictReader(infile))


def load_capacities() -> list[dict[str, str]]:
    return read_csv(CAPACITIES_FILE)


def load_production() -> list[dict[str, str]]:
    return read_csv(PRODUCTION_FILE)


def locate_auxiliary_sources() -> dict[str, Path | None]:
    config = load_sources_config()
    return {
        "lx02": first_existing(config.get("lx02_candidates", [])),
        "lrf2": first_existing(config.get("lrf2_candidates", [])),
    }




def _source_file_state(
    path: Path | None,
    *,
    now: datetime,
    stale_minutes: int,
) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": "",
            "name": "Not found",
            "status": "missing",
            "status_label": "Missing",
            "modified_at": "",
            "modified_at_display": "No file found",
            "age_minutes": None,
            "is_sample": False,
            "is_stale": True,
        }

    modified = datetime.fromtimestamp(path.stat().st_mtime)
    age_minutes = max(0, int((now - modified).total_seconds() // 60))
    normalised_path = str(path).replace("\\", "/")
    is_sample = "data/logistics/input" in normalised_path
    is_stale = age_minutes > max(1, stale_minutes)

    if is_sample:
        status = "sample"
        label = "Sample"
    elif is_stale:
        status = "stale"
        label = "Stale"
    else:
        status = "live"
        label = "Live"

    return {
        "path": str(path),
        "name": path.name,
        "status": status,
        "status_label": label,
        "modified_at": modified.isoformat(timespec="seconds"),
        "modified_at_display": modified.strftime("%d/%m/%Y %H:%M:%S"),
        "age_minutes": age_minutes,
        "is_sample": is_sample,
        "is_stale": is_stale,
    }


def auxiliary_source_state(
    auxiliary: dict[str, Path | None],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now()
    config = load_sources_config()
    stale_minutes = int(config.get("auxiliary_stale_minutes", 45) or 45)

    lx02 = _source_file_state(
        auxiliary.get("lx02"),
        now=now,
        stale_minutes=stale_minutes,
    )
    lrf2 = _source_file_state(
        auxiliary.get("lrf2"),
        now=now,
        stale_minutes=stale_minutes,
    )

    warning_parts = []
    for label, state in (("LX02", lx02), ("LRF2", lrf2)):
        if state["status"] == "missing":
            warning_parts.append(f"{label} is missing")
        elif state["status"] == "sample":
            warning_parts.append(f"{label} is using sample data")
        elif state["status"] == "stale":
            warning_parts.append(
                f"{label} is {state['age_minutes']} minutes old"
            )

    return {
        "lx02": lx02,
        "lrf2": lrf2,
        "stale_minutes": stale_minutes,
        "has_warning": bool(warning_parts),
        "warning_text": "; ".join(warning_parts),
        "live_auxiliary_ready": lx02["status"] == "live" and lrf2["status"] == "live",
        # Backward-compatible fields used by the Milestone 1 templates.
        "lx02_file": lx02["path"],
        "lrf2_file": lrf2["path"],
        "using_sample_lx02": lx02["is_sample"],
        "using_sample_lrf2": lrf2["is_sample"],
    }


def load_staged_orders(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()

    rows = read_rows(path)
    orders: set[str] = set()

    for row in rows:
        storage_bin = clean_text(pick_value(
            row,
            ["Storage Bin", "StorageBin", "Stor. Bin", "Bin"],
        )).upper()

        # A requirement in a dynamic 0234... bin is still waiting for parts or
        # picking. It only becomes staged when the material reaches an SB- bin.
        if not storage_bin.startswith("SB-"):
            continue

        explicit_order = normalise_order_number(pick_value(
            row,
            ["Order No.", "Order Number", "Order", "Production Order"],
        ))
        requirement = normalise_order_number(pick_value(
            row,
            ["Requirement Number", "Requirement No.", "Rqmnt.No.", "Rqmnt No", "Requirement"],
        ))

        if explicit_order.isdigit() and len(explicit_order) >= 10:
            orders.add(explicit_order)
        elif requirement.isdigit() and len(requirement) >= 8:
            if requirement.startswith("200") and len(requirement) >= 10:
                orders.add(requirement)
            else:
                orders.add(f"200{requirement}")

    return orders


def _queue_matches(queue_name: str, prefixes: list[str]) -> bool:
    queue = clean_text(queue_name).upper()
    if not queue:
        return False

    for prefix in prefixes:
        prefix = clean_text(prefix).upper()
        if prefix and (queue == prefix or queue.startswith(prefix) or prefix in queue):
            return True
    return False


def load_picker_state(path: Path | None, areas: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state = {
        area["id"]: {
            "picker_count": 0,
            "pickers": [],
        }
        for area in areas
    }

    if path is None or not path.exists():
        return state

    picker_names = load_picker_names()
    rows = read_rows(path)

    seen_by_area: dict[str, set[str]] = {
        area["id"]: set()
        for area in areas
    }

    for row in rows:
        sap_id = clean_text(pick_value(
            row,
            ["User Name", "User", "SAP ID", "Username"],
        )).upper()
        queue_name = clean_text(pick_value(
            row,
            ["Queue", "Queue Name"],
        ))

        if not sap_id or not queue_name or queue_name.upper() == "DEFAULT":
            continue

        for area in areas:
            if not _queue_matches(queue_name, area.get("picker_queue_prefixes", [])):
                continue
            if sap_id in seen_by_area[area["id"]]:
                continue

            seen_by_area[area["id"]].add(sap_id)
            state[area["id"]]["pickers"].append({
                "sap_id": sap_id,
                "name": picker_names.get(sap_id, sap_id),
                "queue": queue_name,
            })

    for area_id, item in state.items():
        item["pickers"].sort(key=lambda picker: (picker["name"].lower(), picker["sap_id"]))
        item["picker_count"] = len(item["pickers"])

    return state


def source_paths() -> list[Path]:
    auxiliary = locate_auxiliary_sources()
    result = [
        CAPACITIES_FILE,
        PRODUCTION_FILE,
        AREAS_FILE,
        SOURCES_FILE,
        PROJECT_ROOT / "config" / "logistics_picker_names.csv",
    ]
    for value in auxiliary.values():
        if value is not None:
            result.append(value)
    return result
