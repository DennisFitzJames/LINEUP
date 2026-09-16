from pathlib import Path
import csv
import json

PROJECT_ROOT = Path(__file__).parent.parent
OVERRIDES_FILE = PROJECT_ROOT / "config" / "overrides.json"
MASTER_SCHEDULE_FILE = PROJECT_ROOT / "data" / "processed" / "master_schedule.csv"
PRODUCTION_LIST_FILE = PROJECT_ROOT / "data" / "processed" / "production_list_clean.csv"


def default_overrides():
    return {
        "excluded_orders": [],
        "forced_benches": {},
        "forced_next": {},
        "manual_splits": {}
    }


def normalise_overrides(data):
    overrides = default_overrides()

    if isinstance(data, dict):
        overrides.update(data)

    if not isinstance(overrides.get("excluded_orders"), list):
        overrides["excluded_orders"] = []

    if not isinstance(overrides.get("forced_benches"), dict):
        overrides["forced_benches"] = {}

    if not isinstance(overrides.get("forced_next"), dict):
        overrides["forced_next"] = {}

    if not isinstance(overrides.get("manual_splits"), dict):
        overrides["manual_splits"] = {}

    overrides["excluded_orders"] = [
        str(order_number).strip()
        for order_number in overrides["excluded_orders"]
        if str(order_number).strip()
    ]

    overrides["forced_benches"] = {
        str(order_number).strip(): str(bench_id).strip()
        for order_number, bench_id in overrides["forced_benches"].items()
        if str(order_number).strip() and str(bench_id).strip()
    }

    overrides["forced_next"] = {
        str(order_number).strip(): str(bench_id).strip()
        for order_number, bench_id in overrides["forced_next"].items()
        if str(order_number).strip() and str(bench_id).strip()
    }

    overrides["manual_splits"] = {
        str(order_number).strip(): split
        for order_number, split in overrides["manual_splits"].items()
        if str(order_number).strip() and isinstance(split, dict)
    }

    return overrides


def load_overrides():
    if not OVERRIDES_FILE.exists():
        return default_overrides()

    try:
        with open(OVERRIDES_FILE, "r", encoding="utf-8") as infile:
            data = json.load(infile)

    except (json.JSONDecodeError, OSError):
        return default_overrides()

    return normalise_overrides(data)


def save_overrides(data):
    OVERRIDES_FILE.parent.mkdir(exist_ok=True)

    with open(OVERRIDES_FILE, "w", encoding="utf-8") as outfile:
        json.dump(normalise_overrides(data), outfile, indent=4)


def _status_tokens(*values):
    tokens = []
    for value in values:
        text = str(value or "").upper()
        for separator in (",", ";", "/", "|"):
            text = text.replace(separator, " ")
        tokens.extend(part.strip() for part in text.split() if part.strip())
    return set(tokens)


def _to_float(value, default=0.0):
    try:
        text = str(value or "").strip()
        return default if text == "" else float(text)
    except (TypeError, ValueError):
        return default


def _terminal_split_reason(order):
    tokens = _status_tokens(
        order.get("system_status", ""),
        order.get("user_status", ""),
    )

    if "TECO" in tokens:
        return "TECO"

    if "DLV" in tokens:
        return "DLV"

    production_state = str(order.get("production_state", "") or "").strip().upper()
    if production_state == "COMPLETE":
        return "complete"

    remaining_minutes = _to_float(order.get("bench_remaining_minutes", 0), 0)
    if remaining_minutes <= 0 and "CNF" in tokens:
        return "CNF with no remaining work"

    return ""


def _read_order_rows(path):
    rows = {}
    path = Path(path)
    if not path.exists():
        return rows

    try:
        with open(
            path,
            "r",
            encoding="utf-8-sig",
            errors="ignore",
            newline="",
        ) as infile:
            for row in csv.DictReader(infile):
                order_number = str(row.get("order_number", "") or "").strip()
                if order_number:
                    rows[order_number] = row
    except OSError:
        return {}

    return rows


def prune_terminal_manual_splits(
    master_schedule_file=MASTER_SCHEDULE_FILE,
    production_list_file=PRODUCTION_LIST_FILE,
):
    """
    Remove persisted manual split cards once SAP shows the order is terminal.

    Production-list status catches TECO and DLV even when an order has already
    disappeared from the LINEUP capacity summary. Orders missing from both
    sources are deliberately left untouched so an interrupted refresh cannot
    erase planner input.
    """

    overrides = load_overrides()
    manual_splits = overrides.get("manual_splits", {})
    if not manual_splits:
        return {}

    master_orders = _read_order_rows(master_schedule_file)
    production_orders = _read_order_rows(production_list_file)
    if not master_orders and not production_orders:
        return {}

    removed = {}
    for order_number in list(manual_splits):
        production_order = production_orders.get(order_number)
        master_order = master_orders.get(order_number)

        reason = ""
        if production_order is not None:
            reason = _terminal_split_reason(production_order)
        if not reason and master_order is not None:
            reason = _terminal_split_reason(master_order)
        if not reason:
            continue

        manual_splits.pop(order_number, None)
        removed[order_number] = reason

    if removed:
        overrides["manual_splits"] = manual_splits
        save_overrides(overrides)

    return removed

