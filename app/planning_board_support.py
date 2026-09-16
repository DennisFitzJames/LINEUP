from datetime import datetime


DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_text():
    return datetime.now().strftime(
        DATE_TIME_FORMAT
    )


def clean_text(value):
    return str(value or "").strip()


def order_pool(order):
    if not isinstance(order, dict):
        return ""

    return clean_text(
        order.get("scheduling_pool", "")
    )


def bench_pool(bench):
    if not isinstance(bench, dict):
        return ""

    return clean_text(
        bench.get("scheduling_pool", "")
    )


def compatible_bench_ids_for_order(
    order,
    benches,
    open_only=True
):
    if not isinstance(order, dict):
        return []

    required_pool = order_pool(order)

    if not required_pool:
        return []

    compatible_ids = []

    for bench in benches:
        if not isinstance(bench, dict):
            continue

        bench_id = clean_text(
            bench.get("bench_id", "")
        )

        if not bench_id:
            continue

        if open_only:
            is_open = clean_text(
                bench.get("is_open", "yes")
            ).lower()

            if is_open != "yes":
                continue

        if bench_pool(bench) != required_pool:
            continue

        compatible_ids.append(bench_id)

    return compatible_ids


def build_order_board_metadata(
    orders,
    benches
):
    metadata = {}

    for order in orders:
        order_number = clean_text(
            order.get("order_number", "")
        )

        if not order_number:
            continue

        metadata[order_number] = {
            "order_number": order_number,
            "scheduling_pool": order_pool(order),
            "compatible_bench_ids": (
                compatible_bench_ids_for_order(
                    order=order,
                    benches=benches,
                    open_only=True,
                )
            ),
            "remaining_quantity": order.get(
                "remaining_quantity",
                0
            ),
            "sap_remaining_minutes": order.get(
                "bench_remaining_minutes",
                0
            ),
        }

    return metadata


def normalise_board_order_number(raw_item):
    if isinstance(raw_item, dict):
        return clean_text(
            raw_item.get("order_number", "")
        )

    return clean_text(raw_item)


def validate_planning_board_payload(
    payload,
    order_lookup,
    bench_lookup,
    live_benches=None,
):
    """
    Validate the visual Planning Board before it is written.

    Returns a cleaned payload in this form:

        {
            "planning_pool": [
                {"order_number": "123"}
            ],
            "manual_queues": {
                "MV01": [
                    {"order_number": "456"}
                ]
            }
        }

    Raises ValueError for invalid assignments.
    """
    if not isinstance(payload, dict):
        raise ValueError(
            "Invalid Planning Board payload."
        )

    planning_pool = payload.get(
        "planning_pool",
        []
    )

    manual_queues = payload.get(
        "manual_queues",
        {}
    )

    if not isinstance(planning_pool, list):
        raise ValueError(
            "Planning Pool data is invalid."
        )

    if not isinstance(manual_queues, dict):
        raise ValueError(
            "Bench queue data is invalid."
        )

    if live_benches is None:
        live_benches = {}

    used_orders = set()
    clean_pool = []
    clean_queues = {}

    for raw_item in planning_pool:
        order_number = (
            normalise_board_order_number(
                raw_item
            )
        )

        if not order_number:
            continue

        if order_number in used_orders:
            raise ValueError(
                f"Order {order_number} appears "
                "more than once on the Planning Board."
            )

        order = order_lookup.get(
            order_number
        )

        if order is None:
            raise ValueError(
                f"Order {order_number} is not in "
                "the current released SAP order list."
            )

        used_orders.add(order_number)

        clean_pool.append({
            "order_number": order_number
        })

    for raw_bench_id, raw_items in (
        manual_queues.items()
    ):
        bench_id = clean_text(raw_bench_id)

        if not isinstance(raw_items, list):
            raise ValueError(
                f"Queue data for {bench_id or 'unknown bench'} is invalid."
            )

        non_empty_items = [
            item
            for item in raw_items
            if normalise_board_order_number(item)
        ]

        if not non_empty_items:
            continue

        raw_items = non_empty_items


        if not bench_id:
            continue

        bench = bench_lookup.get(
            bench_id
        )

        if bench is None:
            raise ValueError(
                f"Bench {bench_id} does not exist."
            )

        if (
            clean_text(
                bench.get("is_open", "yes")
            ).lower()
            != "yes"
        ):
            raise ValueError(
                f"Bench {bench_id} is closed."
            )

        clean_items = []

        for raw_item in raw_items:
            order_number = (
                normalise_board_order_number(
                    raw_item
                )
            )

            if not order_number:
                continue

            if order_number in used_orders:
                raise ValueError(
                    f"Order {order_number} appears "
                    "more than once on the Planning Board."
                )

            order = order_lookup.get(
                order_number
            )

            if order is None:
                raise ValueError(
                    f"Order {order_number} is not in "
                    "the current released SAP order list."
                )

            order_scheduling_pool = order_pool(
                order
            )

            bench_scheduling_pool = bench_pool(
                bench
            )

            if (
                order_scheduling_pool
                != bench_scheduling_pool
            ):
                raise ValueError(
                    f"Order {order_number} belongs to "
                    f"{order_scheduling_pool}, so it cannot "
                    f"be assigned to {bench_id} "
                    f"({bench_scheduling_pool})."
                )

            used_orders.add(order_number)

            clean_items.append({
                "order_number": order_number
            })

        if clean_items:
            clean_queues[bench_id] = (
                clean_items
            )

    return {
        "planning_pool": clean_pool,
        "manual_queues": clean_queues,
    }


def live_lane_metadata(
    benches,
    live_benches
):
    metadata = {}

    for bench in benches:
        bench_id = clean_text(
            bench.get("bench_id", "")
        )

        if not bench_id:
            continue

        live_state = live_benches.get(
            bench_id
        )

        if live_state:
            live_order_number = clean_text(
                live_state.get(
                    "active_order_number",
                    ""
                )
            )
        else:
            live_order_number = ""

        metadata[bench_id] = {
            "bench_id": bench_id,
            "has_live_wip": bool(
                live_order_number
            ),
            "live_order_number": (
                live_order_number
            ),
        }

    return metadata


def board_state_for_client(
    queue_control,
    benches,
    live_benches
):
    planning_pool = []

    for item in queue_control.get(
        "planning_pool",
        []
    ):
        order_number = clean_text(
            item.get("order_number", "")
        )

        if order_number:
            planning_pool.append(
                order_number
            )

    manual_queues = {}

    for bench in benches:
        bench_id = clean_text(
            bench.get("bench_id", "")
        )

        if not bench_id:
            continue

        manual_queues[bench_id] = []

        for item in (
            queue_control
            .get("manual_queues", {})
            .get(bench_id, [])
        ):
            order_number = clean_text(
                item.get(
                    "order_number",
                    ""
                )
            )

            if order_number:
                manual_queues[
                    bench_id
                ].append(order_number)

    return {
        "planning_pool": planning_pool,
        "manual_queues": manual_queues,
        "live_lanes": live_lane_metadata(
            benches,
            live_benches
        ),
        "generated_at": now_text(),
    }


if __name__ == "__main__":
    print()
    print("===================================")
    print("LINEUP Planning Board Support")
    print("===================================")
    print("Payload validation enabled")
    print("Compatibility validation enabled")
    print("Duplicate protection enabled")
    print()