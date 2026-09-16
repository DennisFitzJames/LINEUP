from pathlib import Path
import csv
from datetime import datetime, date

from overrides import load_overrides
from live_work import (
    get_active_benches,
    apply_live_state_to_order,
    update_live_snapshot,
    cleanup_live_work_for_missing_orders,
)
from queue_control import (
    load_queue_control,
    cleanup_queue_control,
    held_order_numbers,
)
from staffing_overrides import (
    load_staffing_overrides,
    staffing_factor_for_bench,
)
from working_calendar import (
    current_work_minute_start,
    work_minute_to_shift_time,
    planned_day_offset,
    working_day_offset_between,
)
from schedule_insights import (
    SOURCE_LIVE,
    SOURCE_PLANNER,
    SOURCE_SPLIT,
    SOURCE_FORCED,
    SOURCE_STABLE,
    SOURCE_OPTIMISED,
    build_schedule_insight,
    candidate_summary,
)

PROJECT_ROOT = Path(__file__).parent.parent

MASTER_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "master_schedule.csv"
)

BENCHES_FILE = (
    PROJECT_ROOT
    / "config"
    / "benches.csv"
)

SCHEDULED_OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "scheduled_orders.csv"
)

OVERFLOW_OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "overflow_orders.csv"
)

SCHEDULE_BASE_DATE = date.today()


SCHEDULED_COLUMNS = [
    "bench_id",
    "bench_name",
    "scheduling_pool",
    "sequence",
    "order_number",
    "material",
    "material_description",
    "customer",
    "is_australia",
    "priority",
    "scheduled_start",
    "scheduled_finish",
    "target_finish_day_offset",
    "bench_remaining_minutes",
    "sap_remaining_minutes",
    "adjusted_remaining_minutes",
    "staffing_factor",
    "staffing_override_people",
    "planned_start_minute",
    "planned_finish_minute",
    "planned_start_time",
    "planned_finish_time",
    "planned_finish_day_offset",
    "due_status",
    "due_delta_days",
    "due_message",
    "bench_work_centres",
    "bench_operations",
    "system_status",
    "user_status",
    "override_type",
    "override_note",
    "assignment_source",
    "assignment_source_label",
    "assignment_reason",
    "queue_stability",
    "schedule_confidence",
    "confidence_reason",
    "live_active",
    "live_started_at",
    "live_started_remaining_minutes",
    "live_elapsed_minutes",
    "live_sap_refresh_at",
]


OVERFLOW_COLUMNS = [
    "order_number",
    "material",
    "material_description",
    "customer",
    "is_australia",
    "priority",
    "scheduled_start",
    "scheduled_finish",
    "scheduling_pool",
    "bench_remaining_minutes",
    "reason",
]


def parse_int(value, default=0):
    try:
        clean_value = str(value or "").strip()

        if clean_value == "":
            return default

        return int(float(clean_value))

    except (ValueError, TypeError):
        return default


def parse_float(value, default=0.0):
    try:
        clean_value = str(value or "").strip()

        if clean_value == "":
            return default

        return float(clean_value)

    except (ValueError, TypeError):
        return default


def parse_date(value):
    value = str(value or "").strip()

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%d.%m.%Y"
        ).date()

    except ValueError:
        return None


def scheduled_finish_offset(scheduled_finish):
    finish_date = parse_date(scheduled_finish)

    if finish_date is None:
        return ""

    return working_day_offset_between(
        SCHEDULE_BASE_DATE,
        finish_date
    )


def master_refresh_datetime():
    if not MASTER_FILE.exists():
        return datetime.now()

    try:
        return datetime.fromtimestamp(
            MASTER_FILE.stat().st_mtime
        )

    except OSError:
        return datetime.now()


def due_status(
    planned_finish_day_offset,
    target_finish_day_offset
):
    if target_finish_day_offset is None:
        return (
            "UNKNOWN",
            "",
            "No SAP scheduled finish day"
        )

    try:
        planned = int(planned_finish_day_offset)
        target = int(target_finish_day_offset)

    except (ValueError, TypeError):
        return (
            "UNKNOWN",
            "",
            "No SAP scheduled finish day"
        )

    delta = planned - target

    if delta < 0:
        days = abs(delta)

        if days == 1:
            return (
                "AHEAD",
                delta,
                "Ahead by 1 working day"
            )

        return (
            "AHEAD",
            delta,
            f"Ahead by {days} working days"
        )

    if delta == 0:
        return (
            "ON TARGET",
            delta,
            "Finishes on scheduled working day"
        )

    if delta == 1:
        return (
            "LATE",
            delta,
            "Late by 1 working day"
        )

    return (
        "LATE",
        delta,
        f"Late by {delta} working days"
    )


def status_tokens(value):
    return (
        str(value or "")
        .strip()
        .upper()
        .replace(",", " ")
        .replace(";", " ")
        .split()
    )


def row_has_status_token(row, token):
    token = str(token or "").strip().upper()

    if not token:
        return False

    for column_name, value in row.items():
        column_name = str(
            column_name or ""
        ).strip().lower()

        if "status" not in column_name:
            continue

        if token in status_tokens(value):
            return True

    return False


def is_completed_row(row):
    system_status = str(
        row.get("system_status", "") or ""
    ).strip()

    user_status = str(
        row.get("user_status", "") or ""
    ).strip()

    tokens = (
        status_tokens(system_status)
        + status_tokens(user_status)
    )

    if "DLV" in tokens:
        return True

    if row_has_status_token(row, "DLV"):
        return True

    return (
        parse_int(
            row.get("bench_remaining_minutes", 0),
            0
        )
        <= 0
    )


def load_previous_schedule():
    if not SCHEDULED_OUTPUT_FILE.exists():
        return []

    try:
        with open(
            SCHEDULED_OUTPUT_FILE,
            "r",
            encoding="utf-8-sig",
            errors="ignore",
            newline=""
        ) as infile:
            rows = list(csv.DictReader(infile))

    except OSError:
        return []

    rows.sort(
        key=lambda row: (
            str(row.get("bench_id", "") or ""),
            parse_int(row.get("sequence", 0), 0),
        )
    )

    return rows


def load_benches(staffing_state):
    benches = []

    live_start_minute = current_work_minute_start(
        SCHEDULE_BASE_DATE
    )

    with open(
        BENCHES_FILE,
        "r",
        encoding="utf-8-sig",
        errors="ignore",
        newline=""
    ) as infile:
        reader = csv.DictReader(infile)

        for row in reader:
            if (
                str(row.get("is_open", "") or "")
                .strip()
                .lower()
                != "yes"
            ):
                continue

            bench_id = str(
                row.get("bench_id", "") or ""
            ).strip()

            if not bench_id:
                continue

            baseline_people = parse_int(
                row.get("standard_people", 1),
                1
            )

            if baseline_people <= 0:
                baseline_people = 1

            staffing_override = (
                staffing_state
                .get("benches", {})
                .get(bench_id)
            )

            staffing_override_people = ""

            if staffing_override:
                staffing_override_people = parse_int(
                    staffing_override.get("people", 0),
                    0
                )

            staffing_factor = staffing_factor_for_bench(
                bench_id=bench_id,
                baseline_people=baseline_people,
                state=staffing_state
            )

            benches.append({
                "bench_id": bench_id,
                "bench_name": str(
                    row.get("bench_name", "") or ""
                ).strip(),
                "scheduling_pool": str(
                    row.get("scheduling_pool", "") or ""
                ).strip(),
                "baseline_people": baseline_people,
                "staffing_override_people": (
                    staffing_override_people
                ),
                "staffing_factor": staffing_factor,
                "loaded_minutes": live_start_minute,
                "assigned_orders": [],
            })

    return benches


def load_orders():
    orders = []

    with open(
        MASTER_FILE,
        "r",
        encoding="utf-8-sig",
        errors="ignore",
        newline=""
    ) as infile:
        reader = csv.DictReader(infile)

        for row in reader:
            #
            # Production readiness
            #

            if (
                str(row.get("ready_for_production", "no"))
                .strip()
                .lower()
                != "yes"
            ):
                continue


            if is_completed_row(row):
                continue

            sap_minutes = parse_int(
                row.get("bench_remaining_minutes", 0),
                0
            )

            if sap_minutes <= 0:
                continue

            order_number = str(
                row.get("order_number", "") or ""
            ).strip()

            if not order_number:
                continue

            target_quantity = parse_int(
                row.get("target_quantity", 0),
                0
            )

            confirmed_quantity = parse_int(
                row.get("confirmed_quantity", 0),
                0
            )

            remaining_quantity = max(
                0,
                target_quantity - confirmed_quantity
            )

            if remaining_quantity <= 0:
                remaining_quantity = target_quantity

            orders.append({
                "picked": row.get("picked", "no"),
                "ready_for_production": row.get(
                    "ready_for_production",
                    "no"
                ),
                "production_state": row.get(
                    "production_state",
                    "AWAITING_PICKING"
                ),
                "order_number": order_number,
                "material": str(
                    row.get("material", "") or ""
                ).strip(),
                "material_description": str(
                    row.get(
                        "material_description",
                        ""
                    ) or ""
                ).strip(),
                "customer": str(
                    row.get("customer", "") or ""
                ).strip(),
                "is_australia": str(
                    row.get("is_australia", "") or ""
                ).strip(),
                "priority": parse_int(
                    row.get("priority", 0),
                    0
                ),
                "scheduled_start": str(
                    row.get("scheduled_start", "") or ""
                ).strip(),
                "scheduled_finish": str(
                    row.get("scheduled_finish", "") or ""
                ).strip(),
                "scheduled_finish_date": (
                    parse_date(
                        row.get(
                            "scheduled_finish",
                            ""
                        )
                    )
                    or date(2099, 12, 31)
                ),
                "target_finish_day_offset": (
                    scheduled_finish_offset(
                        row.get(
                            "scheduled_finish",
                            ""
                        )
                    )
                ),
                "target_quantity": target_quantity,
                "confirmed_quantity": confirmed_quantity,
                "remaining_quantity": remaining_quantity,
                "scheduling_pool": str(
                    row.get("scheduling_pool", "") or ""
                ).strip(),
                "bench_work_centres": str(
                    row.get(
                        "bench_work_centres",
                        ""
                    ) or ""
                ).strip(),
                "bench_operations": str(
                    row.get(
                        "bench_operations",
                        ""
                    ) or ""
                ).strip(),
                "bench_remaining_minutes": sap_minutes,
                "sap_remaining_minutes": sap_minutes,
                "system_status": str(
                    row.get("system_status", "") or ""
                ).strip(),
                "user_status": str(
                    row.get("user_status", "") or ""
                ).strip(),
                "live_active": "",
                "live_started_at": "",
                "live_started_remaining_minutes": "",
                "live_elapsed_minutes": "",
                "live_sap_refresh_at": "",
            })

    return orders


def effective_minutes_for_bench(
    base_minutes,
    bench
):
    base_minutes = parse_int(base_minutes, 0)

    if base_minutes <= 0:
        return 0

    factor = parse_float(
        bench.get("staffing_factor", 1.0),
        1.0
    )

    if factor <= 0:
        factor = 1.0

    return max(
        1,
        round(base_minutes * factor)
    )


def bench_last_material(bench):
    if not bench["assigned_orders"]:
        return ""

    return bench["assigned_orders"][-1].get(
        "material",
        ""
    )


def bench_has_same_material(bench, material):
    return any(
        assigned_order.get("material") == material
        for assigned_order in bench["assigned_orders"]
    )


def calculate_assignment_penalty(order, bench):
    effective_minutes = effective_minutes_for_bench(
        order["sap_remaining_minutes"],
        bench
    )

    planned_finish_minute = (
        bench["loaded_minutes"]
        + effective_minutes
    )

    finish_offset = planned_day_offset(
        SCHEDULE_BASE_DATE,
        planned_finish_minute,
        is_finish=True
    )

    target_offset = order.get(
        "target_finish_day_offset",
        ""
    )

    try:
        target_offset = int(target_offset)

    except (ValueError, TypeError):
        target_offset = None

    penalty = 0

    if target_offset is None:
        penalty += 5000

    else:
        delta = finish_offset - target_offset

        if delta > 0:
            penalty += delta * 100000

            if order["priority"] > 0:
                penalty += 25000

            if (
                str(order["is_australia"])
                .strip()
                .lower()
                == "yes"
            ):
                penalty += 15000

        elif delta < 0:
            penalty += abs(delta) * 2500

    penalty += planned_finish_minute

    material = order["material"]

    if bench_last_material(bench) == material:
        penalty -= 1200

    elif bench_has_same_material(
        bench,
        material
    ):
        penalty -= 600

    return penalty


def evaluate_eligible_benches(order, benches):
    evaluated = []

    for bench in benches:
        if (
            bench["scheduling_pool"]
            != order["scheduling_pool"]
        ):
            continue

        candidate = dict(bench)

        effective_minutes = effective_minutes_for_bench(
            order["sap_remaining_minutes"],
            bench
        )

        candidate_finish_minute = (
            bench["loaded_minutes"]
            + effective_minutes
        )

        candidate[
            "candidate_effective_minutes"
        ] = effective_minutes

        candidate[
            "candidate_finish_minute"
        ] = candidate_finish_minute

        candidate[
            "candidate_penalty"
        ] = calculate_assignment_penalty(
            order,
            bench
        )

        candidate[
            "candidate_same_last_material"
        ] = (
            bench_last_material(bench)
            == order["material"]
        )

        candidate[
            "candidate_has_same_material"
        ] = bench_has_same_material(
            bench,
            order["material"]
        )

        evaluated.append(candidate)

    evaluated.sort(
        key=lambda candidate: (
            candidate["candidate_penalty"],
            candidate["candidate_finish_minute"],
            candidate["bench_id"],
        )
    )

    return evaluated


def choose_best_bench(order, benches):
    evaluated = evaluate_eligible_benches(
        order,
        benches
    )

    if not evaluated:
        return None, None

    selected_candidate = evaluated[0]

    selected_bench = next(
        (
            bench
            for bench in benches
            if (
                bench["bench_id"]
                == selected_candidate["bench_id"]
            )
        ),
        None
    )

    if selected_bench is None:
        return None, None

    optimisation_details = candidate_summary(
        order=order,
        selected_bench=selected_candidate,
        eligible_benches=evaluated,
        base_date=SCHEDULE_BASE_DATE,
    )

    return selected_bench, optimisation_details


def alpha_label(index):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    if index < len(alphabet):
        return f"Part {alphabet[index]}"

    return f"Part {index + 1}"


def normalise_split_parts(split):
    if not isinstance(split, dict):
        return []

    split_mode = str(
        split.get("split_mode", "") or ""
    ).strip().lower()

    if (
        split_mode == "multi"
        and isinstance(split.get("parts"), list)
    ):
        parts = []

        for index, raw_part in enumerate(
            split.get("parts", [])
        ):
            if not isinstance(raw_part, dict):
                continue

            bench_id = str(
                raw_part.get("bench_id", "") or ""
            ).strip()

            minutes = parse_int(
                raw_part.get("minutes", 0),
                0
            )

            if not bench_id or minutes <= 0:
                continue

            parts.append({
                "part_label": (
                    str(
                        raw_part.get(
                            "part_label",
                            ""
                        ) or ""
                    ).strip()
                    or alpha_label(index)
                ),
                "bench_id": bench_id,
                "quantity": str(
                    raw_part.get("quantity", "") or ""
                ).strip(),
                "minutes": minutes,
            })

        return parts

    parts = []

    bench_a = str(
        split.get("bench_a", "") or ""
    ).strip()

    bench_b = str(
        split.get("bench_b", "") or ""
    ).strip()

    minutes_a = parse_int(
        split.get("minutes_a", 0),
        0
    )

    minutes_b = parse_int(
        split.get("minutes_b", 0),
        0
    )

    if bench_a and minutes_a > 0:
        parts.append({
            "part_label": "Part A",
            "bench_id": bench_a,
            "quantity": str(
                split.get("qty_a", "") or ""
            ).strip(),
            "minutes": minutes_a,
        })

    if bench_b and minutes_b > 0:
        parts.append({
            "part_label": "Part B",
            "bench_id": bench_b,
            "quantity": str(
                split.get("qty_b", "") or ""
            ).strip(),
            "minutes": minutes_b,
        })

    return parts


def previous_stable_orders(
    previous_rows,
    valid_order_numbers,
    active_order_numbers,
    manual_order_numbers,
    split_order_numbers,
    forced_order_numbers,
    held_orders,
    excluded_orders
):
    """
    Preserve one automatic near-term order per bench.

    Live, planner, split and forced assignments are protected elsewhere,
    so they are excluded from the automatic freeze.
    """
    stable_by_bench = {}

    allowed_sources = {
        "",
        SOURCE_OPTIMISED,
        SOURCE_STABLE,
    }

    allowed_override_types = {
        "",
        "AUTO LOCK",
    }

    for row in previous_rows:
        bench_id = str(
            row.get("bench_id", "") or ""
        ).strip()

        order_number = str(
            row.get("order_number", "") or ""
        ).strip()

        assignment_source = str(
            row.get("assignment_source", "") or ""
        ).strip().upper()

        override_type = str(
            row.get("override_type", "") or ""
        ).strip().upper()

        live_active = str(
            row.get("live_active", "") or ""
        ).strip().lower()

        if not bench_id or not order_number:
            continue

        if bench_id in stable_by_bench:
            continue

        if order_number not in valid_order_numbers:
            continue

        if live_active == "yes":
            continue

        if order_number in active_order_numbers:
            continue

        if order_number in manual_order_numbers:
            continue

        if order_number in split_order_numbers:
            continue

        if order_number in forced_order_numbers:
            continue

        if order_number in held_orders:
            continue

        if order_number in excluded_orders:
            continue

        if assignment_source not in allowed_sources:
            continue

        if override_type not in allowed_override_types:
            continue

        stable_by_bench[bench_id] = order_number

    return stable_by_bench


def schedule_orders():
    staffing_state = load_staffing_overrides()
    previous_rows = load_previous_schedule()
    sap_refresh_at = master_refresh_datetime()

    benches = load_benches(staffing_state)
    orders = load_orders()

    valid_order_numbers = {
        order["order_number"]
        for order in orders
    }

    cleanup_live_work_for_missing_orders(
        valid_order_numbers
    )

    cleanup_queue_control(
        valid_order_numbers
    )

    active_benches = get_active_benches()
    queue_control = load_queue_control()

    held_orders = held_order_numbers(
        queue_control
    )

    overrides = load_overrides()

    excluded_orders = {
        str(order_number).strip()
        for order_number in overrides.get(
            "excluded_orders",
            []
        )
        if str(order_number).strip()
    }

    forced_benches = overrides.get(
        "forced_benches",
        {}
    )

    forced_next = overrides.get(
        "forced_next",
        {}
    )

    manual_splits = overrides.get(
        "manual_splits",
        {}
    )

    split_parts_by_order = {
        str(order_number).strip(): (
            normalise_split_parts(split)
        )
        for order_number, split
        in manual_splits.items()
        if str(order_number).strip()
    }

    manual_queues = queue_control.get(
        "manual_queues",
        {}
    )

    manual_order_numbers = {
        str(item.get("order_number", "") or "").strip()
        for items in manual_queues.values()
        for item in items
        if str(
            item.get("order_number", "") or ""
        ).strip()
    }

    split_order_numbers = set(
        split_parts_by_order.keys()
    )

    forced_order_numbers = (
        set(forced_benches.keys())
        | set(forced_next.keys())
    )

    active_order_numbers = {
        str(
            bench_state.get(
                "active_order_number",
                ""
            ) or ""
        ).strip()
        for bench_state in active_benches.values()
        if str(
            bench_state.get(
                "active_order_number",
                ""
            ) or ""
        ).strip()
    }

    orders = [
        order
        for order in orders
        if (
            order["order_number"]
            not in excluded_orders
            and order["order_number"]
            not in held_orders
        )
    ]

    orders.sort(
        key=lambda order: (
            -order["priority"],
            order["scheduled_finish_date"],
            (
                0
                if (
                    order["is_australia"]
                    .lower()
                    == "yes"
                )
                else 1
            ),
            order["material"],
        )
    )

    orders_by_number = {
        order["order_number"]: order
        for order in orders
    }

    stable_by_bench = previous_stable_orders(
        previous_rows=previous_rows,
        valid_order_numbers=set(
            orders_by_number.keys()
        ),
        active_order_numbers=(
            active_order_numbers
        ),
        manual_order_numbers=(
            manual_order_numbers
        ),
        split_order_numbers=(
            split_order_numbers
        ),
        forced_order_numbers=(
            forced_order_numbers
        ),
        held_orders=held_orders,
        excluded_orders=excluded_orders,
    )

    scheduled_order_numbers = set()
    scheduled_split_parts = set()
    overflow_orders = []

    def find_bench_by_id(bench_id):
        return next(
            (
                bench
                for bench in benches
                if bench["bench_id"] == bench_id
            ),
            None
        )

    def compatible_bench(
        order,
        bench_id
    ):
        bench = find_bench_by_id(bench_id)

        if bench is None:
            return None

        if (
            bench["scheduling_pool"]
            != order["scheduling_pool"]
        ):
            return None

        return bench

    def split_part_on_bench(
        order_number,
        bench_id
    ):
        for part in split_parts_by_order.get(
            order_number,
            []
        ):
            if (
                str(part.get("bench_id", "") or "")
                .strip()
                == bench_id
            ):
                return part

        return None

    def assign_order_to_bench(
        order,
        bench,
        assignment_source,
        override_type="",
        override_note="",
        assignment_reason="",
        previous_bench_id="",
        optimisation_details=None,
        base_minutes=None,
        effective_minutes=None,
        is_live=False,
        split_part=False,
    ):
        scheduled_order = dict(order)

        if base_minutes is None:
            base_minutes = parse_int(
                scheduled_order.get(
                    "sap_remaining_minutes",
                    scheduled_order.get(
                        "bench_remaining_minutes",
                        0
                    )
                ),
                0
            )

        else:
            base_minutes = parse_int(
                base_minutes,
                0
            )

        if effective_minutes is None:
            effective_minutes = (
                effective_minutes_for_bench(
                    base_minutes,
                    bench
                )
            )

        else:
            effective_minutes = parse_int(
                effective_minutes,
                0
            )

        scheduled_order[
            "sap_remaining_minutes"
        ] = base_minutes

        scheduled_order[
            "bench_remaining_minutes"
        ] = effective_minutes

        scheduled_order[
            "adjusted_remaining_minutes"
        ] = effective_minutes

        scheduled_order[
            "staffing_factor"
        ] = f"{bench['staffing_factor']:.4f}"

        scheduled_order[
            "staffing_override_people"
        ] = bench.get(
            "staffing_override_people",
            ""
        )

        planned_start_minute = (
            bench["loaded_minutes"]
        )

        planned_finish_minute = (
            planned_start_minute
            + effective_minutes
        )

        finish_offset = planned_day_offset(
            SCHEDULE_BASE_DATE,
            planned_finish_minute,
            is_finish=True
        )

        status, delta, message = due_status(
            finish_offset,
            scheduled_order[
                "target_finish_day_offset"
            ]
        )

        scheduled_order[
            "planned_start_minute"
        ] = planned_start_minute

        scheduled_order[
            "planned_finish_minute"
        ] = planned_finish_minute

        scheduled_order[
            "planned_start_time"
        ] = work_minute_to_shift_time(
            SCHEDULE_BASE_DATE,
            planned_start_minute,
            is_finish=False
        )

        scheduled_order[
            "planned_finish_time"
        ] = work_minute_to_shift_time(
            SCHEDULE_BASE_DATE,
            planned_finish_minute,
            is_finish=True
        )

        scheduled_order[
            "planned_finish_day_offset"
        ] = finish_offset

        scheduled_order["due_status"] = status
        scheduled_order["due_delta_days"] = delta
        scheduled_order["due_message"] = message

        scheduled_order[
            "override_type"
        ] = override_type

        scheduled_order[
            "override_note"
        ] = override_note

        insight = build_schedule_insight(
            order=scheduled_order,
            bench=bench,
            assignment_source=assignment_source,
            due_status=status,
            base_assignment_reason=assignment_reason,
            previous_bench_id=previous_bench_id,
            is_live=is_live,
            split_part=split_part,
            optimisation_details=optimisation_details,
        )

        scheduled_order.update(insight)

        scheduled_order.setdefault(
            "live_active",
            ""
        )

        scheduled_order.setdefault(
            "live_started_at",
            ""
        )

        scheduled_order.setdefault(
            "live_started_remaining_minutes",
            ""
        )

        scheduled_order.setdefault(
            "live_elapsed_minutes",
            ""
        )

        scheduled_order.setdefault(
            "live_sap_refresh_at",
            ""
        )

        bench["assigned_orders"].append(
            scheduled_order
        )

        bench["loaded_minutes"] += (
            effective_minutes
        )

        return scheduled_order

    # --------------------------------------------------
    # 1. Live WIP always remains first.
    # --------------------------------------------------

    for bench_id, bench_state in (
        active_benches.items()
    ):
        order_number = str(
            bench_state.get(
                "active_order_number",
                ""
            ) or ""
        ).strip()

        if (
            not order_number
            or order_number in excluded_orders
            or order_number in held_orders
        ):
            continue

        order = orders_by_number.get(
            order_number
        )

        if order is None:
            continue

        bench = compatible_bench(
            order,
            bench_id
        )

        if bench is None:
            overflow_orders.append({
                **order,
                "reason": (
                    f"Live bench {bench_id} is "
                    f"closed or incompatible"
                ),
            })
            continue

        split_part = split_part_on_bench(
            order_number,
            bench_id
        )

        if split_part:
            live_source_order = dict(order)

            live_source_order[
                "bench_remaining_minutes"
            ] = split_part["minutes"]

            live_source_order[
                "sap_remaining_minutes"
            ] = split_part["minutes"]

            base_minutes = split_part["minutes"]

        else:
            live_source_order = order

            base_minutes = order[
                "sap_remaining_minutes"
            ]

        live_order = apply_live_state_to_order(
            live_source_order,
            bench_state,
            sap_refresh_at=sap_refresh_at,
            staffing_factor=bench[
                "staffing_factor"
            ]
        )

        effective_remaining = parse_int(
            live_order.get(
                "bench_remaining_minutes",
                0
            ),
            0
        )

        update_live_snapshot(
            bench_id=bench_id,
            sap_remaining_minutes=base_minutes,
            effective_remaining_minutes=(
                effective_remaining
            ),
            sap_refresh_at=sap_refresh_at,
            staffing_factor=bench[
                "staffing_factor"
            ],
        )

        note_parts = [
            f"SAP snapshot {base_minutes} min",
            (
                f"remaining estimate "
                f"{effective_remaining} min"
            ),
        ]

        if split_part:
            quantity = str(
                split_part.get("quantity", "")
                or ""
            ).strip()

            override_type = "MANUAL SPLIT"

            override_note = (
                f"{split_part['part_label']}: "
                f"qty {quantity} / "
                f"{effective_remaining} min "
                f"on {bench_id}"
            )

            assignment_reason = (
                "This split part is actively being worked "
                "on this bench and remains locked as current."
            )

            scheduled_split_parts.add(
                (order_number, bench_id)
            )

        else:
            override_type = ""
            override_note = ""

            assignment_reason = (
                "The order is actively being worked on this bench, "
                "so LINEUP keeps it as the current order."
            )

        if override_note:
            override_note += (
                " ・ "
                + " ・ ".join(note_parts)
            )

        else:
            override_note = " ・ ".join(
                note_parts
            )

        assign_order_to_bench(
            order=live_order,
            bench=bench,
            assignment_source=SOURCE_LIVE,
            override_type=override_type,
            override_note=override_note,
            assignment_reason=assignment_reason,
            base_minutes=base_minutes,
            effective_minutes=effective_remaining,
            is_live=True,
            split_part=bool(split_part),
        )

        scheduled_order_numbers.add(
            order_number
        )

    # --------------------------------------------------
    # 2. Planning Board queues remain locked.
    # --------------------------------------------------

    for bench_id, queue_items in (
        manual_queues.items()
    ):
        bench = find_bench_by_id(bench_id)

        for queue_item in queue_items:
            order_number = str(
                queue_item.get(
                    "order_number",
                    ""
                ) or ""
            ).strip()

            if (
                not order_number
                or order_number
                in scheduled_order_numbers
                or order_number
                in split_order_numbers
                or order_number
                in excluded_orders
                or order_number
                in held_orders
            ):
                continue

            order = orders_by_number.get(
                order_number
            )

            if order is None:
                continue

            if (
                bench is None
                or bench["scheduling_pool"]
                != order["scheduling_pool"]
            ):
                overflow_orders.append({
                    **order,
                    "reason": (
                        f"Manual queue bench "
                        f"{bench_id} is closed "
                        f"or incompatible"
                    ),
                })
                continue

            note = str(
                queue_item.get("note", "")
                or ""
            ).strip()

            override_note = (
                f"Planner locked on {bench_id}"
            )

            if note:
                override_note += f": {note}"

            assign_order_to_bench(
                order=order,
                bench=bench,
                assignment_source=SOURCE_PLANNER,
                override_type="PLANNER LOCK",
                override_note=override_note,
                assignment_reason=(
                    f"The planner placed this order on {bench_id} "
                    "using the Planning Board."
                ),
            )

            scheduled_order_numbers.add(
                order_number
            )

    # --------------------------------------------------
    # 3. Split parts remain locked to selected benches.
    # --------------------------------------------------

    for order_number, parts in (
        split_parts_by_order.items()
    ):
        if (
            order_number in excluded_orders
            or order_number in held_orders
        ):
            continue

        order = orders_by_number.get(
            order_number
        )

        if order is None:
            continue

        assigned_any = False

        for part in parts:
            bench_id = str(
                part.get("bench_id", "") or ""
            ).strip()

            part_key = (
                order_number,
                bench_id
            )

            if part_key in scheduled_split_parts:
                assigned_any = True
                continue

            bench = compatible_bench(
                order,
                bench_id
            )

            if bench is None:
                overflow_orders.append({
                    **order,
                    "reason": (
                        f"Split bench {bench_id} "
                        f"is closed or incompatible"
                    ),
                })
                continue

            base_minutes = parse_int(
                part.get("minutes", 0),
                0
            )

            effective_minutes = (
                effective_minutes_for_bench(
                    base_minutes,
                    bench
                )
            )

            quantity = str(
                part.get("quantity", "")
                or ""
            ).strip()

            note = (
                f"{part['part_label']}: "
                f"qty {quantity} / "
                f"{effective_minutes} min "
                f"on {bench_id}"
            )

            assign_order_to_bench(
                order=order,
                bench=bench,
                assignment_source=SOURCE_SPLIT,
                override_type="MANUAL SPLIT",
                override_note=note,
                assignment_reason=(
                    f"The planner split this order and assigned "
                    f"{part['part_label']} to {bench_id}."
                ),
                base_minutes=base_minutes,
                effective_minutes=effective_minutes,
                split_part=True,
            )

            scheduled_split_parts.add(
                part_key
            )

            assigned_any = True

        if assigned_any:
            scheduled_order_numbers.add(
                order_number
            )

    # --------------------------------------------------
    # 4. Existing make-current overrides.
    # --------------------------------------------------

    for order_number, bench_id in (
        forced_next.items()
    ):
        if (
            order_number
            in scheduled_order_numbers
            or order_number in held_orders
            or order_number in excluded_orders
        ):
            continue

        order = orders_by_number.get(
            order_number
        )

        if order is None:
            continue

        bench = compatible_bench(
            order,
            bench_id
        )

        if bench is None:
            overflow_orders.append({
                **order,
                "reason": (
                    f"Make-current bench "
                    f"{bench_id} is closed "
                    f"or incompatible"
                ),
            })
            continue

        assign_order_to_bench(
            order=order,
            bench=bench,
            assignment_source=SOURCE_FORCED,
            override_type="MAKE CURRENT",
            override_note=(
                f"Manually prioritised "
                f"on {bench_id}"
            ),
            assignment_reason=(
                f"The planner used Make Current to prioritise "
                f"this order on {bench_id}."
            ),
        )

        scheduled_order_numbers.add(
            order_number
        )

    # --------------------------------------------------
    # 5. Preserve one prior automatic near-term order.
    # --------------------------------------------------

    for bench_id, order_number in (
        stable_by_bench.items()
    ):
        if order_number in scheduled_order_numbers:
            continue

        order = orders_by_number.get(
            order_number
        )

        if order is None:
            continue

        bench = compatible_bench(
            order,
            bench_id
        )

        if bench is None:
            continue

        assign_order_to_bench(
            order=order,
            bench=bench,
            assignment_source=SOURCE_STABLE,
            override_type="AUTO LOCK",
            override_note=(
                "Preserved from previous schedule "
                "to stabilise the near-term queue"
            ),
            assignment_reason=(
                f"LINEUP preserved this order on {bench_id} because "
                "it was the next automatic order in the previous plan."
            ),
            previous_bench_id=bench_id,
        )

        scheduled_order_numbers.add(
            order_number
        )

    # --------------------------------------------------
    # 6. Optimise all later automatic work.
    # --------------------------------------------------

    for order in orders:
        order_number = order[
            "order_number"
        ]

        if (
            order_number
            in scheduled_order_numbers
            or order_number in held_orders
        ):
            continue

        forced_bench_id = (
            forced_benches.get(order_number)
        )

        if forced_bench_id:
            bench = compatible_bench(
                order,
                forced_bench_id
            )

            if bench is None:
                overflow_orders.append({
                    **order,
                    "reason": (
                        f"Forced bench "
                        f"{forced_bench_id} "
                        f"is closed or incompatible"
                    ),
                })
                continue

            assignment_source = SOURCE_FORCED
            override_type = "FORCED BENCH"

            override_note = (
                f"Forced to {forced_bench_id}"
            )

            assignment_reason = (
                f"An advanced override assigned this order "
                f"to {forced_bench_id}."
            )

            optimisation_details = None

        else:
            bench, optimisation_details = (
                choose_best_bench(
                    order,
                    benches
                )
            )

            assignment_source = SOURCE_OPTIMISED
            override_type = ""
            override_note = ""
            assignment_reason = ""

        if bench is None:
            overflow_orders.append({
                **order,
                "reason": (
                    "No open compatible bench"
                ),
            })
            continue

        assign_order_to_bench(
            order=order,
            bench=bench,
            assignment_source=assignment_source,
            override_type=override_type,
            override_note=override_note,
            assignment_reason=assignment_reason,
            optimisation_details=optimisation_details,
        )

        scheduled_order_numbers.add(
            order_number
        )

    return benches, overflow_orders


def write_outputs(
    benches,
    overflow_orders
):
    SCHEDULED_OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        SCHEDULED_OUTPUT_FILE,
        "w",
        encoding="utf-8",
        newline=""
    ) as outfile:
        writer = csv.writer(outfile)
        writer.writerow(SCHEDULED_COLUMNS)

        scheduled_count = 0

        for bench in benches:
            for sequence, order in enumerate(
                bench["assigned_orders"],
                start=1
            ):
                writer.writerow([
                    bench["bench_id"],
                    bench["bench_name"],
                    bench["scheduling_pool"],
                    sequence,
                    order["order_number"],
                    order["material"],
                    order[
                        "material_description"
                    ],
                    order["customer"],
                    order["is_australia"],
                    order["priority"],
                    order["scheduled_start"],
                    order["scheduled_finish"],
                    order[
                        "target_finish_day_offset"
                    ],
                    order[
                        "bench_remaining_minutes"
                    ],
                    order.get(
                        "sap_remaining_minutes",
                        ""
                    ),
                    order.get(
                        "adjusted_remaining_minutes",
                        order.get(
                            "bench_remaining_minutes",
                            ""
                        )
                    ),
                    order.get(
                        "staffing_factor",
                        "1.0"
                    ),
                    order.get(
                        "staffing_override_people",
                        ""
                    ),
                    order[
                        "planned_start_minute"
                    ],
                    order[
                        "planned_finish_minute"
                    ],
                    order[
                        "planned_start_time"
                    ],
                    order[
                        "planned_finish_time"
                    ],
                    order[
                        "planned_finish_day_offset"
                    ],
                    order["due_status"],
                    order["due_delta_days"],
                    order["due_message"],
                    order[
                        "bench_work_centres"
                    ],
                    order[
                        "bench_operations"
                    ],
                    order["system_status"],
                    order["user_status"],
                    order.get(
                        "override_type",
                        ""
                    ),
                    order.get(
                        "override_note",
                        ""
                    ),
                    order.get(
                        "assignment_source",
                        ""
                    ),
                    order.get(
                        "assignment_source_label",
                        ""
                    ),
                    order.get(
                        "assignment_reason",
                        ""
                    ),
                    order.get(
                        "queue_stability",
                        ""
                    ),
                    order.get(
                        "schedule_confidence",
                        ""
                    ),
                    order.get(
                        "confidence_reason",
                        ""
                    ),
                    order.get(
                        "live_active",
                        ""
                    ),
                    order.get(
                        "live_started_at",
                        ""
                    ),
                    order.get(
                        "live_started_remaining_minutes",
                        ""
                    ),
                    order.get(
                        "live_elapsed_minutes",
                        ""
                    ),
                    order.get(
                        "live_sap_refresh_at",
                        ""
                    ),
                ])

                scheduled_count += 1

    with open(
        OVERFLOW_OUTPUT_FILE,
        "w",
        encoding="utf-8",
        newline=""
    ) as outfile:
        writer = csv.writer(outfile)
        writer.writerow(OVERFLOW_COLUMNS)

        for order in overflow_orders:
            writer.writerow([
                order["order_number"],
                order["material"],
                order[
                    "material_description"
                ],
                order["customer"],
                order["is_australia"],
                order["priority"],
                order["scheduled_start"],
                order["scheduled_finish"],
                order["scheduling_pool"],
                order[
                    "bench_remaining_minutes"
                ],
                order["reason"],
            ])

    return (
        scheduled_count,
        len(overflow_orders)
    )


benches, overflow_orders = schedule_orders()

scheduled_count, overflow_count = write_outputs(
    benches,
    overflow_orders
)

print()
print("===================================")
print("LINEUP Scheduling Complete")
print("===================================")
print(f"Scheduled orders : {scheduled_count}")
print(f"Overflow orders  : {overflow_count}")
print("SAP minutes      : unchanged by default")
print("Staffing         : explicit overrides only")
print("Queue stability  : current + one automatic order")
print("Insights         : assignment reasons and confidence")
print()