"""Import published Shared SAP Data Hub Live CSVs into LINEUP's established schema.

The Data Hub remains the only SAP exporter. No SAP scripts are launched here.
A validation failure stops LINEUP before changing its processed inputs.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "datahub_sources.json"

SOURCE_NAMES = {
    "coois_production_lineup": "coois_production_lineup_latest.csv",
    "coois_capacities_lineup": "coois_capacities_lineup_latest.csv",
    "lx02": "lx02_latest.csv",
    "lrf2": "lrf2_latest.csv",
}

PRODUCTION_COLUMNS = (
    "order_number", "material", "material_description", "scheduled_start",
    "scheduled_finish", "actual_start", "actual_finish", "target_quantity",
    "confirmed_quantity", "customer", "priority", "system_status", "user_status",
)
CAPACITY_COLUMNS = (
    "order_number", "operation", "capacity_category", "work_centre",
    "target_process_hours", "remaining_process_hours", "target_setup_hours",
    "remaining_setup_hours", "target_teardown_hours", "remaining_teardown_hours",
    "remaining_total_hours", "remaining_total_minutes", "earliest_start",
    "latest_finish", "operation_description", "actual_start", "actual_finish",
)

REQUIRED = {
    "coois_production_lineup": {
        "order", "material", "material_description", "schedstart", "sched_fin",
        "act_start", "act_finish", "target_qty", "conf_qty", "customer",
        "priority", "system_status", "userstatus",
    },
    "coois_capacities_lineup": {
        "order", "oper_act", "category", "work_cntr", "trgtproc", "remproc",
        "tgtsetup", "remsetup", "teardn_sch", "rem_teardn",
        "earl_start", "earl_start__2", "lat_finish", "lat_finish__2",
        "op_description_1", "act_start", "act_start__2",
        "act_finish", "act_finish__2",
    },
    "lx02": {"storagebin", "rqmnt_no", "material", "available_stock"},
    "lrf2": {"user_name", "queue"},
}

class DataHubInputError(RuntimeError):
    pass


def config():
    with CONFIG.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise DataHubInputError("config/datahub_sources.json must be an object")
    return data


def is_enabled():
    return config().get("enabled") is True


def hub_root():
    path = os.environ.get("LINEUP_DATAHUB_ROOT") or config().get("publish_root")
    if not path or not str(path).strip():
        raise DataHubInputError("Configure publish_root or LINEUP_DATAHUB_ROOT")
    return Path(path)


def source_path(job_id):
    if job_id not in SOURCE_NAMES:
        raise DataHubInputError(f"Unrecognised Data Hub report: {job_id}")
    return hub_root() / "Live" / job_id / SOURCE_NAMES[job_id]


def _read_source(job_id, *, now=None):
    path = source_path(job_id)
    if not path.is_file():
        raise DataHubInputError(f"Missing {job_id} dataset: {path}")
    before = path.stat()
    max_age = int(config().get("max_age_minutes", 120))
    age = ((time.time() if now is None else now) - before.st_mtime) / 60
    if age > max_age:
        raise DataHubInputError(f"Stale {job_id} dataset ({age:.0f} min old, limit {max_age}): {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            missing = REQUIRED[job_id] - set(fields)
            if missing:
                raise DataHubInputError(f"{job_id}: missing Data Hub columns: {sorted(missing)}")
            if len(fields) != len(set(fields)):
                raise DataHubInputError(f"{job_id}: duplicate CSV headers")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DataHubInputError(f"Could not read {job_id}: {exc}") from exc
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise DataHubInputError(f"{job_id} was updated during this read; retry")
    if job_id in ("coois_production_lineup", "coois_capacities_lineup", "lx02") and not rows:
        raise DataHubInputError(f"{job_id} has zero rows; refusing to clear planning data")
    if any(None in row for row in rows):
        raise DataHubInputError(f"{job_id}: malformed CSV row with extra fields")
    return rows


def _join_datetime(day, clock):
    day, clock = (day or "").strip(), (clock or "").strip()
    if not day:
        return ""
    if clock in ("", "00:00:00", "00:00"):
        # Midnight can be genuine; keep it when the associated date is provided.
        return f"{day} {clock}".strip() if clock else day
    return f"{day} {clock}"


def _number(row, key):
    value = (row.get(key) or "").strip().replace(",", "")
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError as exc:
        raise DataHubInputError(f"Invalid numeric {key}={value!r} for order {row.get('order')}") from exc


def build_production(rows):
    keymap = {
        "order_number": "order", "material": "material",
        "material_description": "material_description",
        "scheduled_start": "schedstart", "scheduled_finish": "sched_fin",
        "actual_start": "act_start", "actual_finish": "act_finish",
        "target_quantity": "target_qty", "confirmed_quantity": "conf_qty",
        "customer": "customer", "priority": "priority",
        "system_status": "system_status", "user_status": "userstatus",
    }
    converted = []
    for row in rows:
        result = {key: (row.get(source) or "").strip() for key, source in keymap.items()}
        if not result["order_number"].isdigit():
            raise DataHubInputError("Production row has invalid order identifier")
        converted.append(result)
    return converted


def build_capacities(rows):
    mapping = {
        "order_number": "order", "operation": "oper_act",
        "capacity_category": "category", "work_centre": "work_cntr",
        "target_process_hours": "trgtproc", "remaining_process_hours": "remproc",
        "target_setup_hours": "tgtsetup", "remaining_setup_hours": "remsetup",
        "target_teardown_hours": "teardn_sch", "remaining_teardown_hours": "rem_teardn",
        "operation_description": "op_description_1",
    }
    converted = []
    for row in rows:
        result = {key: (row.get(source) or "").strip() for key, source in mapping.items()}
        if not result["order_number"].isdigit() or not result["operation"]:
            raise DataHubInputError("Capacity row has invalid order or operation identifier")
        rem = sum(_number(row, k) for k in ("remproc", "remsetup", "rem_teardn"))
        result["remaining_total_hours"] = str(round(rem, 3))
        result["remaining_total_minutes"] = str(round(rem * 60))
        result["earliest_start"] = _join_datetime(row.get("earl_start"), row.get("earl_start__2"))
        result["latest_finish"] = _join_datetime(row.get("lat_finish"), row.get("lat_finish__2"))
        result["actual_start"] = _join_datetime(row.get("act_start"), row.get("act_start__2"))
        result["actual_finish"] = _join_datetime(row.get("act_finish"), row.get("act_finish__2"))
        converted.append(result)
    return converted


def validate():
    """Validate all 4 sources, including the two logistics feeds, before writing."""
    raws = {name: _read_source(name) for name in SOURCE_NAMES}
    production = build_production(raws["coois_production_lineup"])
    capacities = build_capacities(raws["coois_capacities_lineup"])
    production_ids = {row["order_number"] for row in production}
    if not (production_ids & {row["order_number"] for row in capacities}):
        raise DataHubInputError("No production orders overlap capacities; check selected SAP layouts")
    return raws, production, capacities


def _encode_csv(fields, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _publish_pair(items):
    staged = []
    backups = {}
    completed = []
    try:
        for target, data in items:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name+".", suffix=".tmp", delete=False) as temp:
                temp.write(data)
                staged.append((target, Path(temp.name)))
        for target, _ in items:
            backups[target] = target.read_bytes() if target.exists() else None
        for target, tmp in staged:
            os.replace(tmp, target)
            completed.append(target)
    except Exception:
        for target in reversed(completed):
            data = backups[target]
            if data is None:
                target.unlink(missing_ok=True)
            else:
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as restore:
                    restore.write(data)
                    restore_path = Path(restore.name)
                os.replace(restore_path, target)
        raise
    finally:
        for _, temp in staged:
            temp.unlink(missing_ok=True)


def refresh_production_and_capacities():
    if not is_enabled():
        raise DataHubInputError("Data Hub source mode is not enabled")
    raws, production, capacities = validate()
    output = ROOT / "data" / "processed"
    _publish_pair([
        (output / "production_list_clean.csv", _encode_csv(PRODUCTION_COLUMNS, production)),
        (output / "capacities_clean.csv", _encode_csv(CAPACITY_COLUMNS, capacities)),
    ])
    print(f"Data Hub import successful: {len(production)} production orders, "
          f"{len(capacities)} capacity operations, "
          f"{len(raws['lx02'])} LX02 rows, {len(raws['lrf2'])} LRF2 rows.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--is-enabled", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    try:
        if args.is_enabled:
            return 0 if is_enabled() else 1
        if args.validate:
            raws, prod, cap = validate()
            print(f"VALID: production={len(prod)}, capacities={len(cap)}, "
                  f"LX02={len(raws['lx02'])}, LRF2={len(raws['lrf2'])}")
            return 0
        refresh_production_and_capacities()
        return 0
    except (DataHubInputError, OSError, ValueError) as exc:
        print(f"Data Hub source validation FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
