from pathlib import Path
import csv

PROJECT_ROOT = Path(__file__).parent.parent

MASTER_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "master_schedule.csv"
)


def parse_int(value, default=0):
    try:
        text = str(value or "").strip()

        if text == "":
            return default

        return int(float(text))

    except (ValueError, TypeError):
        return default


def calculate_remaining_quantity(row):
    target_quantity = parse_int(
        row.get("target_quantity", 0),
        0,
    )

    confirmed_quantity = parse_int(
        row.get("confirmed_quantity", 0),
        0,
    )

    remaining_quantity = max(
        0,
        target_quantity - confirmed_quantity,
    )

    if remaining_quantity <= 0:
        remaining_quantity = target_quantity

    return (
        target_quantity,
        confirmed_quantity,
        remaining_quantity,
    )


def read_master_rows():
    if not MASTER_FILE.exists():
        return []

    try:
        with open(
            MASTER_FILE,
            "r",
            encoding="utf-8-sig",
            errors="ignore",
            newline="",
        ) as infile:
            return list(csv.DictReader(infile))

    except OSError:
        return []


def normalise_production_state(row):
    """
    Read the production state exactly as written by merge_data.py.

    This repository deliberately does not recalculate
    business rules.
    """

    return (
        str(row.get("production_state", "") or "")
        .strip()
        .upper()
    )


def build_order(row):
    order_number = str(
        row.get("order_number", "") or ""
    ).strip()

    if not order_number:
        return None

    system_status = str(
        row.get("system_status", "") or ""
    ).strip()

    user_status = str(
        row.get("user_status", "") or ""
    ).strip()

    remaining_minutes = parse_int(
        row.get("bench_remaining_minutes", 0),
        0,
    )

    (
        target_quantity,
        confirmed_quantity,
        remaining_quantity,
    ) = calculate_remaining_quantity(row)

    production_state = normalise_production_state(row)

    if not production_state:
        production_state = "UNKNOWN"

    return {
        "order_number": order_number,
        "material": str(
            row.get("material", "") or ""
        ).strip(),
        "material_description": str(
            row.get("material_description", "") or ""
        ).strip(),
        "customer": str(
            row.get("customer", "") or ""
        ).strip(),
        "is_australia": str(
            row.get("is_australia", "") or ""
        ).strip(),
        "priority": parse_int(
            row.get("priority", 0),
            0,
        ),
        "scheduled_start": str(
            row.get("scheduled_start", "") or ""
        ).strip(),
        "scheduled_finish": str(
            row.get("scheduled_finish", "") or ""
        ).strip(),
        "target_quantity": target_quantity,
        "confirmed_quantity": confirmed_quantity,
        "remaining_quantity": remaining_quantity,
        "scheduling_pool": str(
            row.get("scheduling_pool", "") or ""
        ).strip(),
        "bench_work_centres": str(
            row.get("bench_work_centres", "") or ""
        ).strip(),
        "bench_operations": str(
            row.get("bench_operations", "") or ""
        ).strip(),
        "bench_remaining_minutes": remaining_minutes,
        "system_status": system_status,
        "user_status": user_status,
        "is_released": str(
            row.get("is_released", "no") or "no"
        ).strip().lower(),
        "picked": str(
            row.get("picked", "no") or "no"
        ).strip().lower(),
        "ready_for_production": str(
            row.get("ready_for_production", "no") or "no"
        ).strip().lower(),
        "production_state": production_state,
    }


def load_master_orders(include_complete=False):
    orders = []

    for row in read_master_rows():
        order = build_order(row)

        if order is None:
            continue

        if (
            not include_complete
            and order["production_state"] == "COMPLETE"
        ):
            continue

        if (
            not include_complete
            and order["bench_remaining_minutes"] <= 0
        ):
            continue

        orders.append(order)

    orders.sort(
        key=lambda order: (
            order["scheduling_pool"],
            -order["priority"],
            order["scheduled_finish"],
            order["material"],
            order["order_number"],
        )
    )

    return orders


def load_ready_orders():
    return [
        order
        for order in load_master_orders()
        if order["production_state"] == "READY"
    ]


def load_awaiting_picking_orders():
    return [
        order
        for order in load_master_orders()
        if order["production_state"] == "AWAITING_PICKING"
    ]


def load_completed_orders():
    return [
        order
        for order in load_master_orders(
            include_complete=True
        )
        if order["production_state"] == "COMPLETE"
    ]


def load_order_lookup(include_complete=False):
    return {
        order["order_number"]: order
        for order in load_master_orders(
            include_complete=include_complete
        )
    }


def load_ready_order_lookup():
    return {
        order["order_number"]: order
        for order in load_ready_orders()
    }