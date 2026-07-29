from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent.parent
OVERRIDES_FILE = PROJECT_ROOT / "config" / "overrides.json"


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