from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from .config import load_area_config
from .source_data import (
    load_capacities,
    load_picker_state,
    load_production,
    load_staged_orders,
    locate_auxiliary_sources,
    auxiliary_source_state,
)
from .utils import (
    clean_text,
    determine_order_status,
    display_date,
    forecast_remaining,
    is_next_week,
    iso_date,
    normalise_order_number,
    parse_date,
    to_float,
)


def _capacity_category_is_two(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return True
    try:
        return int(float(text)) == 2
    except ValueError:
        return False


def _normalised_work_centre_set(values: list[Any] | tuple[Any, ...] | set[Any]) -> set[str]:
    return {
        clean_text(value).upper()
        for value in values
        if clean_text(value)
    }


def _order_allowed_for_area(
    area: dict[str, Any],
    order_work_centres: set[str],
) -> bool:
    required = _normalised_work_centre_set(
        area.get("require_any_work_centres", [])
    )
    excluded = _normalised_work_centre_set(
        area.get("exclude_if_order_has_work_centres", [])
    )

    if required and not order_work_centres.intersection(required):
        return False

    if excluded and order_work_centres.intersection(excluded):
        return False

    return True


def _build_capacity_groups(
    capacities: list[dict[str, str]],
    areas: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    work_centre_to_area: dict[str, dict[str, Any]] = {}
    for area in areas:
        for work_centre in area.get("work_centres", []):
            work_centre_to_area[clean_text(work_centre).upper()] = area

    order_work_centres: dict[str, set[str]] = defaultdict(set)
    eligible_rows: list[tuple[dict[str, str], str, str]] = []

    for row in capacities:
        if not _capacity_category_is_two(row.get("capacity_category", "")):
            continue

        order_number = normalise_order_number(row.get("order_number", ""))
        work_centre = clean_text(row.get("work_centre", "")).upper()
        if not order_number or not work_centre:
            continue

        order_work_centres[order_number].add(work_centre)
        eligible_rows.append((row, order_number, work_centre))

    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for row, order_number, work_centre in eligible_rows:
        area = work_centre_to_area.get(work_centre)
        if area is None:
            continue

        if not _order_allowed_for_area(
            area,
            order_work_centres.get(order_number, set()),
        ):
            continue

        key = (area["id"], order_number)
        if key not in groups:
            groups[key] = {
                "area_id": area["id"],
                "area_name": area["name"],
                "order_number": order_number,
                "work_centres": set(),
                "operations": set(),
                "target_process_hours": 0.0,
                "target_setup_hours": 0.0,
                "target_teardown_hours": 0.0,
                "remaining_process_hours": 0.0,
                "remaining_setup_hours": 0.0,
                "remaining_teardown_hours": 0.0,
                "operation_starts": [],
                "operation_finishes": [],
            }

        group = groups[key]
        group["work_centres"].add(work_centre)

        operation = clean_text(row.get("operation", ""))
        if operation:
            group["operations"].add(operation)

        # The old BW plan displays target process hours as HRS Required.
        # Fallbacks keep older processed files usable during the transition.
        group["target_process_hours"] += to_float(
            row.get("target_process_hours", row.get("remaining_process_hours", 0))
        )
        group["target_setup_hours"] += to_float(row.get("target_setup_hours", 0))
        group["target_teardown_hours"] += to_float(row.get("target_teardown_hours", 0))
        group["remaining_process_hours"] += to_float(row.get("remaining_process_hours", 0))
        group["remaining_setup_hours"] += to_float(row.get("remaining_setup_hours", 0))
        group["remaining_teardown_hours"] += to_float(row.get("remaining_teardown_hours", 0))

        operation_start = clean_text(row.get("earliest_start", ""))
        operation_finish = clean_text(row.get("latest_finish", ""))
        if operation_start:
            group["operation_starts"].append(operation_start)
        if operation_finish:
            group["operation_finishes"].append(operation_finish)

    return groups


def _production_lookup(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        order_number = normalise_order_number(row.get("order_number", ""))
        if order_number:
            result[order_number] = row
    return result


def _order_sort_key(order: dict[str, Any]) -> tuple:
    scheduled = parse_date(order.get("scheduled_start", ""))
    return (
        scheduled is None,
        scheduled or date.max,
        order.get("priority_sort", 999999),
        order.get("order_number", ""),
    )


def _reverse_date_sort_key(order: dict[str, Any]) -> tuple:
    scheduled = parse_date(order.get("scheduled_start", ""))
    ordinal = scheduled.toordinal() if scheduled else 0
    return (-ordinal, order.get("order_number", ""))


def _priority_sort(value: Any) -> int:
    text = clean_text(value)
    if text == "":
        return 999999
    try:
        return int(float(text))
    except ValueError:
        return 999998


def build_logistics_payload(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    today = now.date()

    config = load_area_config()
    areas = config.get("areas", [])
    forecast_config = config.get("forecast", {})
    planning_window = config.get("planning_window", {})
    planning_start = today - timedelta(days=today.weekday())
    planning_end = planning_start + timedelta(days=11)
    include_overdue = bool(planning_window.get("include_overdue", True))

    capacities = load_capacities()
    production = _production_lookup(load_production())
    auxiliary = locate_auxiliary_sources()
    staged_orders = load_staged_orders(auxiliary.get("lx02"))
    picker_state = load_picker_state(auxiliary.get("lrf2"), areas)

    capacity_groups = _build_capacity_groups(capacities, areas)

    area_payloads: dict[str, dict[str, Any]] = {}
    snapshot_rows: list[dict[str, Any]] = []

    for area in areas:
        area_payloads[area["id"]] = {
            "id": area["id"],
            "name": area["name"],
            "accent": area.get("accent", "#6d5dfc"),
            "display_order": area.get("display_order", 999),
            "orders_per_person": area.get("orders_per_person", 0),
            "picker_count": picker_state.get(area["id"], {}).get("picker_count", 0),
            "pickers": picker_state.get(area["id"], {}).get("pickers", []),
            "active_orders": [],
            "picked_orders": [],
            "teco_orders": [],
        }

    for (area_id, order_number), capacity in capacity_groups.items():
        production_row = production.get(order_number)
        if production_row is None:
            continue

        system_status = clean_text(production_row.get("system_status", ""))
        user_status = clean_text(production_row.get("user_status", ""))
        status = determine_order_status(
            system_status=system_status,
            user_status=user_status,
            staged_from_lx02=order_number in staged_orders,
        )

        scheduled_start = clean_text(production_row.get("scheduled_start", ""))
        scheduled_finish = clean_text(production_row.get("scheduled_finish", ""))
        actual_start = clean_text(production_row.get("actual_start", ""))
        actual_finish = clean_text(production_row.get("actual_finish", ""))
        scheduled_date = parse_date(scheduled_start)

        # LINEUP's shared COOIS export is broader than the old BW export.
        # Keep the logistics view bounded through Friday of next week while
        # retaining overdue backlog when configured.
        if scheduled_date:
            if scheduled_date > planning_end:
                continue
            if not include_overdue and scheduled_date < planning_start:
                continue

        remaining_hours = (
            capacity["remaining_process_hours"]
            + capacity["remaining_setup_hours"]
            + capacity["remaining_teardown_hours"]
        )

        order = {
            "row_key": f"{area_id}:{order_number}",
            "area_id": area_id,
            "area_name": capacity["area_name"],
            "order_number": order_number,
            "scheduled_start": iso_date(scheduled_start),
            "scheduled_start_display": display_date(scheduled_start),
            "scheduled_finish": iso_date(scheduled_finish),
            "scheduled_finish_display": display_date(scheduled_finish),
            "actual_start": iso_date(actual_start),
            "actual_start_display": display_date(actual_start),
            "actual_finish": iso_date(actual_finish),
            "actual_finish_display": display_date(actual_finish),
            "material": clean_text(production_row.get("material", "")),
            "material_description": clean_text(
                production_row.get("material_description", "")
            ),
            "target_quantity": clean_text(production_row.get("target_quantity", "")),
            "confirmed_quantity": clean_text(
                production_row.get("confirmed_quantity", "")
            ),
            "customer": clean_text(production_row.get("customer", "")),
            "priority": clean_text(production_row.get("priority", "")),
            "priority_sort": _priority_sort(production_row.get("priority", "")),
            "system_status": system_status,
            "user_status": user_status,
            "status": status,
            "hours_required": round(capacity["target_process_hours"], 2),
            "target_setup_hours": round(capacity["target_setup_hours"], 2),
            "target_teardown_hours": round(capacity["target_teardown_hours"], 2),
            "remaining_hours": round(remaining_hours, 2),
            "remaining_process_hours": round(
                capacity["remaining_process_hours"], 2
            ),
            "remaining_setup_hours": round(
                capacity["remaining_setup_hours"], 2
            ),
            "remaining_teardown_hours": round(
                capacity["remaining_teardown_hours"], 2
            ),
            "work_centres": sorted(capacity["work_centres"]),
            "operations": sorted(capacity["operations"]),
            "is_overdue": bool(scheduled_date and scheduled_date < today),
            "is_next_week": is_next_week(scheduled_date, today=today),
        }

        snapshot_rows.append({
            "order_number": order_number,
            "area_id": area_id,
            "area_name": capacity["area_name"],
            "work_centres": ", ".join(order["work_centres"]),
            "scheduled_start": order["scheduled_start"],
            "scheduled_finish": order["scheduled_finish"],
            "status": status,
            "system_status": system_status,
            "user_status": user_status,
            "hours_required": order["hours_required"],
            "remaining_hours": order["remaining_hours"],
        })

        area_payload = area_payloads[area_id]
        if status in {"REL", "CRTD"}:
            area_payload["active_orders"].append(order)
        elif status == "STAGED":
            area_payload["picked_orders"].append(order)
        elif status == "TECO":
            area_payload["teco_orders"].append(order)

    overview_areas = []
    tomorrow = today + timedelta(days=1)

    for area in areas:
        payload = area_payloads[area["id"]]
        active_orders = payload["active_orders"]
        picked_orders = payload["picked_orders"]
        teco_orders = payload["teco_orders"]

        active_orders.sort(key=_order_sort_key)
        picked_orders.sort(key=_reverse_date_sort_key)
        teco_orders.sort(key=_reverse_date_sort_key)

        picker_count = payload["picker_count"]
        orders_per_person = payload["orders_per_person"]
        full_day_target = picker_count * orders_per_person
        forecast_count = forecast_remaining(
            picker_count=picker_count,
            orders_per_person=orders_per_person,
            now=now,
            start_text=str(forecast_config.get("workday_start", "07:50")),
            workday_hours=float(forecast_config.get("workday_hours", 9.0) or 9.0),
        )

        forecast_position = min(len(active_orders), max(0, int(forecast_count)))

        target_position = 0
        for index, order in enumerate(active_orders):
            if parse_date(order.get("scheduled_start", "")) == tomorrow:
                target_position = index + 1

        payload["active_count"] = len(active_orders)
        payload["picked_count"] = len(picked_orders)
        payload["teco_count"] = len(teco_orders)
        payload["overdue_count"] = sum(
            1 for order in active_orders if order["is_overdue"]
        )
        payload["target_hours"] = round(
            sum(order["hours_required"] for order in active_orders), 2
        )
        payload["remaining_hours"] = round(
            sum(order["remaining_hours"] for order in active_orders), 2
        )
        payload["full_day_target"] = full_day_target
        payload["forecast_count"] = round(forecast_count, 1)
        payload["forecast_position"] = forecast_position
        payload["target_position"] = target_position
        payload["target_date"] = tomorrow.isoformat()
        payload["target_date_display"] = tomorrow.strftime("%d/%m/%Y")
        payload["updated_at"] = now.isoformat(timespec="seconds")

        # The sidebar stays compact; full history is available in the tracker.
        payload["picked_orders"] = picked_orders[:30]
        payload["teco_orders"] = teco_orders[:20]

        overview_areas.append({
            "id": payload["id"],
            "name": payload["name"],
            "accent": payload["accent"],
            "display_order": payload["display_order"],
            "active_count": payload["active_count"],
            "picked_count": payload["picked_count"],
            "teco_count": payload["teco_count"],
            "overdue_count": payload["overdue_count"],
            "picker_count": payload["picker_count"],
            "target_hours": payload["target_hours"],
            "remaining_hours": payload["remaining_hours"],
            "forecast_count": payload["forecast_count"],
        })

    overview_areas.sort(key=lambda item: (item["display_order"], item["name"]))

    totals = {
        "active_count": sum(area["active_count"] for area in overview_areas),
        "picked_count": sum(area["picked_count"] for area in overview_areas),
        "teco_count": sum(area["teco_count"] for area in overview_areas),
        "overdue_count": sum(area["overdue_count"] for area in overview_areas),
        "picker_count": sum(area["picker_count"] for area in overview_areas),
        "target_hours": round(sum(area["target_hours"] for area in overview_areas), 2),
        "remaining_hours": round(
            sum(area["remaining_hours"] for area in overview_areas), 2
        ),
    }

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_at_display": now.strftime("%d/%m/%Y %H:%M:%S"),
        "refresh_seconds": int(config.get("refresh_seconds", 60) or 60),
        "totals": totals,
        "areas": overview_areas,
        "area_details": area_payloads,
        "snapshot_rows": snapshot_rows,
        "planning_window": {
            "start": planning_start.isoformat(),
            "end": planning_end.isoformat(),
            "end_display": planning_end.strftime("%d/%m/%Y"),
            "include_overdue": include_overdue,
        },
        "source_state": auxiliary_source_state(auxiliary, now=now),
    }
