from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AREAS_FILE = PROJECT_ROOT / "config" / "logistics_areas.json"
SOURCES_FILE = PROJECT_ROOT / "config" / "logistics_sources.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as infile:
            return json.load(infile)
    except (OSError, json.JSONDecodeError):
        return default


def load_area_config() -> dict[str, Any]:
    data = load_json(AREAS_FILE, {"areas": []})
    areas = data.get("areas", [])
    if not isinstance(areas, list):
        areas = []

    cleaned = []
    for area in areas:
        if not isinstance(area, dict):
            continue
        area_id = str(area.get("id", "")).strip()
        name = str(area.get("name", "")).strip()
        if not area_id or not name:
            continue
        item = dict(area)
        item["id"] = area_id
        item["name"] = name
        item["work_centres"] = [
            str(value).strip().upper()
            for value in area.get("work_centres", [])
            if str(value).strip()
        ]
        item["picker_queue_prefixes"] = [
            str(value).strip().upper()
            for value in area.get("picker_queue_prefixes", [])
            if str(value).strip()
        ]
        item["orders_per_person"] = int(area.get("orders_per_person", 0) or 0)
        item["display_order"] = int(area.get("display_order", 999) or 999)
        cleaned.append(item)

    cleaned.sort(key=lambda item: (item["display_order"], item["name"]))
    data["areas"] = cleaned
    return data


def load_sources_config() -> dict[str, Any]:
    return load_json(SOURCES_FILE, {})


def resolve_candidate_paths(values: list[str]) -> list[Path]:
    result = []
    for value in values or []:
        path = Path(str(value))
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        result.append(path)
    return result


def first_existing(values: list[str]) -> Path | None:
    for path in resolve_candidate_paths(values):
        if path.exists():
            return path
    return None


def load_picker_names() -> dict[str, str]:
    config = load_sources_config()
    value = str(config.get("picker_names_file", "")).strip()
    if not value:
        return {}

    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        return {}

    names: dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as infile:
        for row in csv.DictReader(infile):
            sap_id = str(row.get("sap_id", "")).strip().upper()
            picker_name = str(row.get("picker_name", "")).replace("\xa0", " ").strip()
            if sap_id:
                names[sap_id] = picker_name or sap_id
    return names
