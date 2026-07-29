from pathlib import Path
import csv
from datetime import date

from overrides import load_overrides
from queue_control import (
    load_queue_control,
    held_order_numbers,
)
from staffing_overrides import (
    load_staffing_overrides,
    staffing_factor_for_bench,
)
from working_calendar import (
    current_work_minute_start,
    planned_day_offset,
    work_minute_to_shift_time,
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

SCHEDULED_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "scheduled_orders.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "split_recommendations.csv"
)

SCHEDULE_BASE_DATE = date.today()

SPLIT_RECOMMENDATION_MAX_TARGET_OFFSET = 1

CANDIDATE_PERCENTAGES = [
    50,
    60,
    40,
    70,
    30,
]

OUTPUT_COLUMNS = [
    "order_number",
    "material",
    "material_description",
    "scheduling_pool",
    "current_bench_id",
    "current_bench_name",
    "current_assignment_source",
    "target_finish_day_offset",
    "current_finish_day_offset",
    "current_finish_time",
    "current_late_days",
    "recommended_second_bench_id",
    "recommended_second_bench_name",
    "recommended_finish_day_offset",
    "recommended_finish_time",
    "recommended_late_days",
    "lateness_reduction_days",
    "recommendation_status",
    "recommendation_message",
    "recommendation_reason",
    "base_late_orders",
    "recommended_late_orders",
    "late_orders_change",
    "base_total_late_days",
    "recommended_total_late_days",
    "total_late_days_change",
    "other_orders_made_late",
    "target_quantity",
    "confirmed_quantity",
    "remaining_quantity",
    "current_bench_quantity",
    "second_bench_quantity",
    "current_bench_base_minutes",
    "second_bench_base_minutes",
    "current_bench_minutes",
    "second_bench_minutes",
    "current_bench_staffing_factor",
    "second_bench_staffing_factor",
    "current_bench_staffing_override_people",
    "second_bench_staffing_override_people",
    "split_percent_a",
    "split_percent_b",
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


def normalise_text(value):
    return str(value or "").strip()


def read_csv(path):
    if not path.exists():
        return []

    with open(
        path,
        "r",
        encoding="utf-8-sig",
        errors="ignore",
        newline=""
    ) as infile:
        return list(csv.DictReader(infile))


def load_open_benches(staffing_state):
    benches = {}

    for row in read_csv(BENCHES_FILE):
        if (
            normalise_text(row.get("is_open", ""))
            .lower()
            != "yes"
        ):
            continue

        bench_id = normalise_text(
            row.get("bench_id", "")
        )

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
            state=staffing_state,
        )

        benches[bench_id] = {
            "bench_id": bench_id,
            "bench_name": normalise_text(
                row.get("bench_name", "")
            ),
            "scheduling_pool": normalise_text(
                row.get("scheduling_pool", "")
            ),
            "baseline_people": baseline_people,
            "staffing_factor": staffing_factor,
            "staffing_override_people": (
                staffing_override_people
            ),
        }

    return benches


def load_master_lookup():
    lookup = {}

    for row in read_csv(MASTER_FILE):
        order_number = normalise_text(
            row.get("order_number", "")
        )

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

        lookup[order_number] = {
            "target_quantity": target_quantity,
            "confirmed_quantity": confirmed_quantity,
            "remaining_quantity": remaining_quantity,
            "sap_remaining_minutes": parse_int(
                row.get("bench_remaining_minutes", 0),
                0
            ),
        }

    return lookup


def split_integer_total(total, parts):
    total = parse_int(total, 0)
    parts = parse_int(parts, 0)

    if parts <= 0:
        return []

    base = total // parts
    remainder = total % parts

    values = []

    for index in range(parts):
        value = base

        if index < remainder:
            value += 1

        values.append(value)

    return values


def split_minutes_by_quantities(
    total_minutes,
    quantities
):
    total_minutes = parse_int(
        total_minutes,
        0
    )

    if total_minutes <= 0:
        return [
            0
            for _quantity in quantities
        ]

    quantity_total = sum(
        parse_int(quantity, 0)
        for quantity in quantities
    )

    if quantity_total <= 0:
        return split_integer_total(
            total_minutes,
            len(quantities)
        )

    minutes = []

    for quantity in quantities:
        quantity = parse_int(
            quantity,
            0
        )

        minutes.append(
            round(
                total_minutes
                * quantity
                / quantity_total
            )
        )

    difference = (
        total_minutes
        - sum(minutes)
    )

    index = 0

    while difference != 0 and minutes:
        target_index = index % len(minutes)

        if difference > 0:
            minutes[target_index] += 1
            difference -= 1

        else:
            if minutes[target_index] > 1:
                minutes[target_index] -= 1
                difference += 1

        index += 1

        if index > 10000:
            break

    return minutes


def effective_minutes_for_bench(
    base_minutes,
    bench
):
    base_minutes = parse_int(
        base_minutes,
        0
    )

    if base_minutes <= 0:
        return 0

    staffing_factor = parse_float(
        bench.get("staffing_factor", 1.0),
        1.0
    )

    if staffing_factor <= 0:
        staffing_factor = 1.0

    return max(
        1,
        round(
            base_minutes
            * staffing_factor
        )
    )


def calculate_lateness(
    finish_offset,
    target_offset
):
    try:
        finish_offset = int(
            finish_offset
        )

        target_offset = int(
            target_offset
        )

    except (ValueError, TypeError):
        return 0

    return max(
        0,
        finish_offset - target_offset
    )


def immediate_future_candidate(row):
    target_offset = parse_int(
        row.get(
            "target_finish_day_offset",
            ""
        ),
        None
    )

    if target_offset is None:
        return False

    return (
        target_offset
        <= SPLIT_RECOMMENDATION_MAX_TARGET_OFFSET
    )


def planner_controlled_order_numbers(
    queue_control
):
    order_numbers = set()

    for items in (
        queue_control
        .get("manual_queues", {})
        .values()
    ):
        for item in items:
            order_number = normalise_text(
                item.get(
                    "order_number",
                    ""
                )
            )

            if order_number:
                order_numbers.add(
                    order_number
                )

    return order_numbers


def live_order_numbers(
    scheduled_rows
):
    return {
        normalise_text(
            row.get("order_number", "")
        )
        for row in scheduled_rows
        if (
            normalise_text(
                row.get("live_active", "")
            ).lower()
            == "yes"
            and normalise_text(
                row.get("order_number", "")
            )
        )
    }


def build_bench_loads(
    scheduled_rows,
    benches
):
    start_minute = current_work_minute_start(
        SCHEDULE_BASE_DATE
    )

    bench_loads = {
        bench_id: start_minute
        for bench_id in benches.keys()
    }

    for row in scheduled_rows:
        bench_id = normalise_text(
            row.get("bench_id", "")
        )

        if bench_id not in bench_loads:
            continue

        finish_minute = parse_int(
            row.get(
                "planned_finish_minute",
                0
            ),
            0
        )

        if (
            finish_minute
            > bench_loads[bench_id]
        ):
            bench_loads[
                bench_id
            ] = finish_minute

    return bench_loads


def assignment_source_is_automatic(row):
    source = normalise_text(
        row.get(
            "assignment_source",
            ""
        )
    ).upper()

    if not source:
        override_type = normalise_text(
            row.get(
                "override_type",
                ""
            )
        ).upper()

        return override_type in (
            "",
            "AUTO LOCK",
        )

    return source in (
        "OPTIMISED",
        "STABLE",
    )


def staffing_explanation(
    bench
):
    override_people = bench.get(
        "staffing_override_people",
        ""
    )

    factor = parse_float(
        bench.get("staffing_factor", 1.0),
        1.0
    )

    if not override_people:
        return (
            "SAP duration is used unchanged "
            "because no staffing override is active."
        )

    if factor > 1.0:
        return (
            f"{override_people} people are manually set, "
            f"so duration is increased by a factor of "
            f"{factor:.2f}."
        )

    if factor < 1.0:
        return (
            f"{override_people} people are manually set, "
            f"so duration is reduced by a factor of "
            f"{factor:.2f}."
        )

    return (
        f"{override_people} people are manually set, "
        "but this does not change the SAP duration."
    )


def recommendation_reason_text(
    current_bench,
    second_bench,
    current_finish_time,
    recommended_finish_time,
    current_late_days,
    recommended_late_days,
    percent_a,
    percent_b,
):
    reason_parts = [
        (
            f"The current plan on "
            f"{current_bench['bench_id']} "
            f"finishes at {current_finish_time}."
        ),
        (
            f"Moving {percent_b}% of the remaining "
            f"work to {second_bench['bench_id']} "
            f"produces a combined finish of "
            f"{recommended_finish_time}."
        ),
    ]

    if recommended_late_days == 0:
        reason_parts.append(
            "This recovers the order to its "
            "SAP scheduled finish day."
        )

    elif recommended_late_days < current_late_days:
        reason_parts.append(
            f"This reduces lateness from "
            f"{current_late_days} to "
            f"{recommended_late_days} "
            f"working day(s)."
        )

    reason_parts.append(
        staffing_explanation(
            current_bench
        )
    )

    reason_parts.append(
        staffing_explanation(
            second_bench
        )
    )

    return " ".join(reason_parts)


def build_recommendations():
    scheduled_rows = read_csv(
        SCHEDULED_FILE
    )

    staffing_state = (
        load_staffing_overrides()
    )

    benches = load_open_benches(
        staffing_state
    )

    master_lookup = load_master_lookup()

    overrides = load_overrides()

    manual_splits = {
        normalise_text(order_number)
        for order_number
        in overrides.get(
            "manual_splits",
            {}
        ).keys()
        if normalise_text(order_number)
    }

    excluded_orders = {
        normalise_text(order_number)
        for order_number
        in overrides.get(
            "excluded_orders",
            []
        )
        if normalise_text(order_number)
    }

    forced_orders = {
        normalise_text(order_number)
        for order_number
        in (
            list(
                overrides.get(
                    "forced_benches",
                    {}
                ).keys()
            )
            + list(
                overrides.get(
                    "forced_next",
                    {}
                ).keys()
            )
        )
        if normalise_text(order_number)
    }

    queue_control = load_queue_control()

    held_orders = held_order_numbers(
        queue_control
    )

    planner_orders = (
        planner_controlled_order_numbers(
            queue_control
        )
    )

    live_orders = live_order_numbers(
        scheduled_rows
    )

    bench_loads = build_bench_loads(
        scheduled_rows,
        benches
    )

    recommendations = []

    seen_orders = set()

    for row in scheduled_rows:
        order_number = normalise_text(
            row.get("order_number", "")
        )

        if not order_number:
            continue

        if order_number in seen_orders:
            continue

        seen_orders.add(order_number)

        if order_number in manual_splits:
            continue

        if order_number in excluded_orders:
            continue

        if order_number in held_orders:
            continue

        if order_number in planner_orders:
            continue

        if order_number in live_orders:
            continue

        if order_number in forced_orders:
            continue

        if not assignment_source_is_automatic(
            row
        ):
            continue

        if not immediate_future_candidate(
            row
        ):
            continue

        if (
            normalise_text(
                row.get("due_status", "")
            ).upper()
            != "LATE"
        ):
            continue

        current_bench_id = normalise_text(
            row.get("bench_id", "")
        )

        current_bench = benches.get(
            current_bench_id
        )

        if current_bench is None:
            continue

        scheduling_pool = normalise_text(
            row.get("scheduling_pool", "")
        )

        target_offset = parse_int(
            row.get(
                "target_finish_day_offset",
                ""
            ),
            None
        )

        current_finish_offset = parse_int(
            row.get(
                "planned_finish_day_offset",
                ""
            ),
            None
        )

        current_start_minute = parse_int(
            row.get(
                "planned_start_minute",
                0
            ),
            0
        )

        current_finish_minute = parse_int(
            row.get(
                "planned_finish_minute",
                0
            ),
            0
        )

        if (
            target_offset is None
            or current_finish_offset is None
        ):
            continue

        current_late_days = (
            calculate_lateness(
                current_finish_offset,
                target_offset
            )
        )

        if current_late_days <= 0:
            continue

        master_row = master_lookup.get(
            order_number,
            {}
        )

        target_quantity = parse_int(
            master_row.get(
                "target_quantity",
                0
            ),
            0
        )

        confirmed_quantity = parse_int(
            master_row.get(
                "confirmed_quantity",
                0
            ),
            0
        )

        remaining_quantity = parse_int(
            master_row.get(
                "remaining_quantity",
                0
            ),
            0
        )

        base_total_minutes = parse_int(
            master_row.get(
                "sap_remaining_minutes",
                0
            ),
            0
        )

        if remaining_quantity <= 1:
            continue

        if base_total_minutes <= 1:
            continue

        best_candidate = None

        for (
            second_bench_id,
            second_bench
        ) in benches.items():
            if (
                second_bench_id
                == current_bench_id
            ):
                continue

            if (
                second_bench[
                    "scheduling_pool"
                ]
                != scheduling_pool
            ):
                continue

            second_start_minute = (
                bench_loads.get(
                    second_bench_id,
                    current_work_minute_start(
                        SCHEDULE_BASE_DATE
                    )
                )
            )

            for percent_a in (
                CANDIDATE_PERCENTAGES
            ):
                if (
                    percent_a <= 0
                    or percent_a >= 100
                ):
                    continue

                qty_a = round(
                    remaining_quantity
                    * percent_a
                    / 100
                )

                qty_a = max(
                    1,
                    min(
                        qty_a,
                        remaining_quantity - 1
                    )
                )

                qty_b = (
                    remaining_quantity
                    - qty_a
                )

                (
                    base_minutes_a,
                    base_minutes_b,
                ) = split_minutes_by_quantities(
                    base_total_minutes,
                    [
                        qty_a,
                        qty_b,
                    ]
                )

                if (
                    base_minutes_a <= 0
                    or base_minutes_b <= 0
                ):
                    continue

                effective_minutes_a = (
                    effective_minutes_for_bench(
                        base_minutes_a,
                        current_bench
                    )
                )

                effective_minutes_b = (
                    effective_minutes_for_bench(
                        base_minutes_b,
                        second_bench
                    )
                )

                current_part_finish_minute = (
                    current_start_minute
                    + effective_minutes_a
                )

                second_part_finish_minute = (
                    second_start_minute
                    + effective_minutes_b
                )

                recommended_finish_minute = max(
                    current_part_finish_minute,
                    second_part_finish_minute
                )

                recommended_finish_offset = (
                    planned_day_offset(
                        SCHEDULE_BASE_DATE,
                        recommended_finish_minute,
                        is_finish=True
                    )
                )

                recommended_late_days = (
                    calculate_lateness(
                        recommended_finish_offset,
                        target_offset
                    )
                )

                lateness_reduction_days = (
                    current_late_days
                    - recommended_late_days
                )

                if lateness_reduction_days <= 0:
                    continue

                total_effective_minutes = (
                    effective_minutes_a
                    + effective_minutes_b
                )

                score = (
                    lateness_reduction_days,
                    -recommended_late_days,
                    -recommended_finish_minute,
                    -total_effective_minutes,
                    -abs(50 - percent_a),
                )

                candidate = {
                    "score": score,
                    "recommended_second_bench_id": (
                        second_bench_id
                    ),
                    "recommended_second_bench_name": (
                        second_bench[
                            "bench_name"
                        ]
                    ),
                    "recommended_finish_minute": (
                        recommended_finish_minute
                    ),
                    "recommended_finish_day_offset": (
                        recommended_finish_offset
                    ),
                    "recommended_late_days": (
                        recommended_late_days
                    ),
                    "lateness_reduction_days": (
                        lateness_reduction_days
                    ),
                    "current_bench_quantity": qty_a,
                    "second_bench_quantity": qty_b,
                    "current_bench_base_minutes": (
                        base_minutes_a
                    ),
                    "second_bench_base_minutes": (
                        base_minutes_b
                    ),
                    "current_bench_minutes": (
                        effective_minutes_a
                    ),
                    "second_bench_minutes": (
                        effective_minutes_b
                    ),
                    "split_percent_a": percent_a,
                    "split_percent_b": (
                        100 - percent_a
                    ),
                    "second_bench": second_bench,
                }

                if (
                    best_candidate is None
                    or candidate["score"]
                    > best_candidate["score"]
                ):
                    best_candidate = candidate

        if best_candidate is None:
            continue

        current_finish_time = (
            normalise_text(
                row.get(
                    "planned_finish_time",
                    ""
                )
            )
            or work_minute_to_shift_time(
                SCHEDULE_BASE_DATE,
                current_finish_minute,
                is_finish=True
            )
        )

        recommended_finish_time = (
            work_minute_to_shift_time(
                SCHEDULE_BASE_DATE,
                best_candidate[
                    "recommended_finish_minute"
                ],
                is_finish=True
            )
        )

        base_late_orders = (
            1
            if current_late_days > 0
            else 0
        )

        recommended_late_orders = (
            1
            if best_candidate[
                "recommended_late_days"
            ] > 0
            else 0
        )

        late_orders_change = (
            base_late_orders
            - recommended_late_orders
        )

        base_total_late_days = (
            current_late_days
        )

        recommended_total_late_days = (
            best_candidate[
                "recommended_late_days"
            ]
        )

        total_late_days_change = (
            base_total_late_days
            - recommended_total_late_days
        )

        if (
            best_candidate[
                "recommended_late_days"
            ]
            == 0
        ):
            recommendation_status = (
                "RECOVERABLE"
            )

            recommendation_message = (
                "Split can recover this order "
                "to its scheduled finish day."
            )

        else:
            recommendation_status = (
                "REDUCES LATENESS"
            )

            recommendation_message = (
                f"Split reduces lateness by "
                f"{best_candidate['lateness_reduction_days']} "
                f"working day(s)."
            )

        recommendation_reason = (
            recommendation_reason_text(
                current_bench=current_bench,
                second_bench=best_candidate[
                    "second_bench"
                ],
                current_finish_time=(
                    current_finish_time
                ),
                recommended_finish_time=(
                    recommended_finish_time
                ),
                current_late_days=(
                    current_late_days
                ),
                recommended_late_days=(
                    best_candidate[
                        "recommended_late_days"
                    ]
                ),
                percent_a=(
                    best_candidate[
                        "split_percent_a"
                    ]
                ),
                percent_b=(
                    best_candidate[
                        "split_percent_b"
                    ]
                ),
            )
        )

        recommendations.append({
            "order_number": order_number,
            "material": row.get(
                "material",
                ""
            ),
            "material_description": row.get(
                "material_description",
                ""
            ),
            "scheduling_pool": (
                scheduling_pool
            ),
            "current_bench_id": (
                current_bench_id
            ),
            "current_bench_name": (
                current_bench[
                    "bench_name"
                ]
            ),
            "current_assignment_source": (
                normalise_text(
                    row.get(
                        "assignment_source",
                        ""
                    )
                )
                or "OPTIMISED"
            ),
            "target_finish_day_offset": (
                target_offset
            ),
            "current_finish_day_offset": (
                current_finish_offset
            ),
            "current_finish_time": (
                current_finish_time
            ),
            "current_late_days": (
                current_late_days
            ),
            "recommended_second_bench_id": (
                best_candidate[
                    "recommended_second_bench_id"
                ]
            ),
            "recommended_second_bench_name": (
                best_candidate[
                    "recommended_second_bench_name"
                ]
            ),
            "recommended_finish_day_offset": (
                best_candidate[
                    "recommended_finish_day_offset"
                ]
            ),
            "recommended_finish_time": (
                recommended_finish_time
            ),
            "recommended_late_days": (
                best_candidate[
                    "recommended_late_days"
                ]
            ),
            "lateness_reduction_days": (
                best_candidate[
                    "lateness_reduction_days"
                ]
            ),
            "recommendation_status": (
                recommendation_status
            ),
            "recommendation_message": (
                recommendation_message
            ),
            "recommendation_reason": (
                recommendation_reason
            ),
            "base_late_orders": (
                base_late_orders
            ),
            "recommended_late_orders": (
                recommended_late_orders
            ),
            "late_orders_change": (
                late_orders_change
            ),
            "base_total_late_days": (
                base_total_late_days
            ),
            "recommended_total_late_days": (
                recommended_total_late_days
            ),
            "total_late_days_change": (
                total_late_days_change
            ),
            "other_orders_made_late": 0,
            "target_quantity": (
                target_quantity
            ),
            "confirmed_quantity": (
                confirmed_quantity
            ),
            "remaining_quantity": (
                remaining_quantity
            ),
            "current_bench_quantity": (
                best_candidate[
                    "current_bench_quantity"
                ]
            ),
            "second_bench_quantity": (
                best_candidate[
                    "second_bench_quantity"
                ]
            ),
            "current_bench_base_minutes": (
                best_candidate[
                    "current_bench_base_minutes"
                ]
            ),
            "second_bench_base_minutes": (
                best_candidate[
                    "second_bench_base_minutes"
                ]
            ),
            "current_bench_minutes": (
                best_candidate[
                    "current_bench_minutes"
                ]
            ),
            "second_bench_minutes": (
                best_candidate[
                    "second_bench_minutes"
                ]
            ),
            "current_bench_staffing_factor": (
                f"{parse_float(
                    current_bench.get(
                        'staffing_factor',
                        1.0
                    ),
                    1.0
                ):.4f}"
            ),
            "second_bench_staffing_factor": (
                f"{parse_float(
                    best_candidate[
                        'second_bench'
                    ].get(
                        'staffing_factor',
                        1.0
                    ),
                    1.0
                ):.4f}"
            ),
            "current_bench_staffing_override_people": (
                current_bench.get(
                    "staffing_override_people",
                    ""
                )
            ),
            "second_bench_staffing_override_people": (
                best_candidate[
                    "second_bench"
                ].get(
                    "staffing_override_people",
                    ""
                )
            ),
            "split_percent_a": (
                best_candidate[
                    "split_percent_a"
                ]
            ),
            "split_percent_b": (
                best_candidate[
                    "split_percent_b"
                ]
            ),
        })

    recommendations.sort(
        key=lambda row: (
            -parse_int(
                row.get(
                    "lateness_reduction_days",
                    0
                ),
                0
            ),
            parse_int(
                row.get(
                    "target_finish_day_offset",
                    99
                ),
                99
            ),
            parse_int(
                row.get(
                    "recommended_late_days",
                    99
                ),
                99
            ),
            row.get(
                "order_number",
                ""
            ),
        )
    )

    return recommendations


def write_recommendations(
    recommendations
):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
        newline=""
    ) as outfile:
        writer = csv.DictWriter(
            outfile,
            fieldnames=OUTPUT_COLUMNS
        )

        writer.writeheader()

        for row in recommendations:
            writer.writerow(row)


recommendations = build_recommendations()

write_recommendations(
    recommendations
)

print()
print("===================================")
print("LINEUP Split Recommendations Complete")
print("===================================")
print(
    f"Recommendations : "
    f"{len(recommendations)}"
)
print(
    "Window          : "
    "due today or next working day only"
)
print(
    "SAP minutes     : "
    "used unchanged by default"
)
print(
    "Staffing        : "
    "explicit overrides only"
)
print(
    "Planner work    : "
    "live, held, split, forced and board orders excluded"
)
print(
    f"Output          : "
    f"{OUTPUT_FILE.name}"
)
print()