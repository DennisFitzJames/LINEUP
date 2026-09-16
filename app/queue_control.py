from pathlib import Path
import json
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
QUEUE_CONTROL_FILE = PROJECT_ROOT / "config" / "queue_control.json"

DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_text():
    return datetime.now().strftime(DATE_TIME_FORMAT)


def default_queue_control():
    return {
        "version": 2,
        "planning_pool": [],
        "manual_queues": {},
        "held_orders": {}
    }


def clean_order_number(value):
    return str(value or "").strip()


def clean_queue_item(item):
    if not isinstance(item, dict):
        return None

    order_number = clean_order_number(item.get("order_number", ""))

    if not order_number:
        return None

    return {
        "order_number": order_number,
        "added_at": str(item.get("added_at", "")).strip(),
        "added_by": str(item.get("added_by", "control")).strip() or "control",
        "note": str(item.get("note", "")).strip(),
    }


def clean_pool_item(item):
    if not isinstance(item, dict):
        return None

    order_number = clean_order_number(item.get("order_number", ""))

    if not order_number:
        return None

    return {
        "order_number": order_number,
        "added_at": str(item.get("added_at", "")).strip(),
        "added_by": str(item.get("added_by", "control")).strip() or "control",
        "note": str(item.get("note", "")).strip(),
    }


def clean_held_order(order_number, held_data):
    order_number = clean_order_number(order_number)

    if not order_number:
        return None

    if not isinstance(held_data, dict):
        held_data = {}

    return {
        "order_number": order_number,
        "bench_id": str(held_data.get("bench_id", "")).strip(),
        "held_at": str(held_data.get("held_at", "")).strip(),
        "held_by": str(held_data.get("held_by", "control")).strip() or "control",
        "reason": str(held_data.get("reason", "")).strip(),
        "note": str(held_data.get("note", "")).strip(),
    }


def normalise_queue_control(data):
    state = default_queue_control()

    if isinstance(data, dict):
        state.update(data)

    state["version"] = 2

    if not isinstance(state.get("planning_pool"), list):
        state["planning_pool"] = []

    if not isinstance(state.get("manual_queues"), dict):
        state["manual_queues"] = {}

    if not isinstance(state.get("held_orders"), dict):
        state["held_orders"] = {}

    clean_planning_pool = []
    seen_pool_orders = set()

    for item in state["planning_pool"]:
        clean_item = clean_pool_item(item)

        if clean_item is None:
            continue

        order_number = clean_item["order_number"]

        if order_number in seen_pool_orders:
            continue

        seen_pool_orders.add(order_number)
        clean_planning_pool.append(clean_item)

    clean_manual_queues = {}

    for bench_id, items in state["manual_queues"].items():
        bench_id = str(bench_id or "").strip()

        if not bench_id:
            continue

        if not isinstance(items, list):
            continue

        clean_items = []
        seen_orders = set()

        for item in items:
            clean_item = clean_queue_item(item)

            if clean_item is None:
                continue

            order_number = clean_item["order_number"]

            if order_number in seen_orders:
                continue

            seen_orders.add(order_number)
            clean_items.append(clean_item)

        if clean_items:
            clean_manual_queues[bench_id] = clean_items

    clean_held_orders = {}

    for order_number, held_data in state["held_orders"].items():
        clean_held = clean_held_order(order_number, held_data)

        if clean_held is None:
            continue

        clean_held_orders[clean_held["order_number"]] = clean_held

    state["planning_pool"] = clean_planning_pool
    state["manual_queues"] = clean_manual_queues
    state["held_orders"] = clean_held_orders

    return state


def load_queue_control():
    if not QUEUE_CONTROL_FILE.exists():
        state = default_queue_control()
        save_queue_control(state)
        return state

    try:
        with open(QUEUE_CONTROL_FILE, "r", encoding="utf-8") as infile:
            data = json.load(infile)

    except (json.JSONDecodeError, OSError):
        state = default_queue_control()
        save_queue_control(state)
        return state

    return normalise_queue_control(data)


def save_queue_control(data):
    QUEUE_CONTROL_FILE.parent.mkdir(parents=True, exist_ok=True)

    state = normalise_queue_control(data)

    with open(QUEUE_CONTROL_FILE, "w", encoding="utf-8") as outfile:
        json.dump(state, outfile, indent=4)


def manual_queue_order_numbers(state=None):
    if state is None:
        state = load_queue_control()

    order_numbers = set()

    for items in state.get("manual_queues", {}).values():
        for item in items:
            order_number = clean_order_number(item.get("order_number", ""))

            if order_number:
                order_numbers.add(order_number)

    return order_numbers


def planning_pool_order_numbers(state=None):
    if state is None:
        state = load_queue_control()

    order_numbers = set()

    for item in state.get("planning_pool", []):
        order_number = clean_order_number(item.get("order_number", ""))

        if order_number:
            order_numbers.add(order_number)

    return order_numbers


def held_order_numbers(state=None):
    if state is None:
        state = load_queue_control()

    return set(
        clean_order_number(order_number)
        for order_number in state.get("held_orders", {}).keys()
        if clean_order_number(order_number)
    )


def remove_order_from_all_manual_queues(order_number, state=None):
    order_number = clean_order_number(order_number)

    if not order_number:
        return 0, state if state is not None else load_queue_control()

    if state is None:
        state = load_queue_control()

    removed_count = 0

    for bench_id, items in list(state.get("manual_queues", {}).items()):
        original_count = len(items)

        state["manual_queues"][bench_id] = [
            item for item in items
            if clean_order_number(item.get("order_number", "")) != order_number
        ]

        removed_count += original_count - len(state["manual_queues"][bench_id])

        if not state["manual_queues"][bench_id]:
            state["manual_queues"].pop(bench_id, None)

    return removed_count, state


def remove_order_from_planning_pool_state(order_number, state):
    order_number = clean_order_number(order_number)

    if not order_number:
        return 0

    items = state.get("planning_pool", [])
    original_count = len(items)

    state["planning_pool"] = [
        item for item in items
        if clean_order_number(item.get("order_number", "")) != order_number
    ]

    return original_count - len(state["planning_pool"])


def add_order_to_planning_pool(order_number, note="", added_by="control"):
    order_number = clean_order_number(order_number)

    if not order_number:
        raise ValueError("Order number is required.")

    state = load_queue_control()

    remove_order_from_planning_pool_state(order_number, state)

    state.setdefault("planning_pool", [])
    state["planning_pool"].append({
        "order_number": order_number,
        "added_at": now_text(),
        "added_by": str(added_by or "control").strip() or "control",
        "note": str(note or "").strip(),
    })

    save_queue_control(state)

    return state


def remove_order_from_planning_pool(order_number):
    order_number = clean_order_number(order_number)

    state = load_queue_control()
    removed_count = remove_order_from_planning_pool_state(order_number, state)
    save_queue_control(state)

    return removed_count


def clear_planning_pool():
    state = load_queue_control()
    removed_count = len(state.get("planning_pool", []))
    state["planning_pool"] = []
    save_queue_control(state)

    return removed_count


def add_order_to_manual_queue(
    bench_id,
    order_number,
    note="",
    added_by="control",
    remove_from_other_queues=True,
    remove_from_pool=True
):
    bench_id = str(bench_id or "").strip()
    order_number = clean_order_number(order_number)

    if not bench_id:
        raise ValueError("Bench ID is required.")

    if not order_number:
        raise ValueError("Order number is required.")

    state = load_queue_control()

    if remove_from_other_queues:
        remove_order_from_all_manual_queues(order_number, state)

    if remove_from_pool:
        remove_order_from_planning_pool_state(order_number, state)

    state.setdefault("manual_queues", {})
    state["manual_queues"].setdefault(bench_id, [])

    existing_items = state["manual_queues"][bench_id]

    for item in existing_items:
        if clean_order_number(item.get("order_number", "")) == order_number:
            item["note"] = str(note or "").strip()
            item["added_by"] = str(added_by or "control").strip() or "control"

            if not item.get("added_at"):
                item["added_at"] = now_text()

            state.setdefault("held_orders", {})
            state["held_orders"].pop(order_number, None)

            save_queue_control(state)
            return state

    state["manual_queues"][bench_id].append({
        "order_number": order_number,
        "added_at": now_text(),
        "added_by": str(added_by or "control").strip() or "control",
        "note": str(note or "").strip(),
    })

    state.setdefault("held_orders", {})
    state["held_orders"].pop(order_number, None)

    save_queue_control(state)

    return state


def remove_order_from_manual_queue(bench_id, order_number):
    bench_id = str(bench_id or "").strip()
    order_number = clean_order_number(order_number)

    state = load_queue_control()

    if not bench_id:
        removed_count, state = remove_order_from_all_manual_queues(
            order_number,
            state
        )
        save_queue_control(state)
        return removed_count

    items = state.get("manual_queues", {}).get(bench_id, [])
    original_count = len(items)

    state["manual_queues"][bench_id] = [
        item for item in items
        if clean_order_number(item.get("order_number", "")) != order_number
    ]

    removed_count = original_count - len(state["manual_queues"][bench_id])

    if not state["manual_queues"][bench_id]:
        state["manual_queues"].pop(bench_id, None)

    save_queue_control(state)

    return removed_count


def move_order_in_manual_queue(bench_id, order_number, direction):
    bench_id = str(bench_id or "").strip()
    order_number = clean_order_number(order_number)
    direction = str(direction or "").strip().lower()

    if direction not in ("up", "down"):
        raise ValueError("Direction must be up or down.")

    state = load_queue_control()
    items = state.get("manual_queues", {}).get(bench_id, [])

    index = None

    for item_index, item in enumerate(items):
        if clean_order_number(item.get("order_number", "")) == order_number:
            index = item_index
            break

    if index is None:
        return False

    if direction == "up":
        if index == 0:
            return False

        items[index - 1], items[index] = items[index], items[index - 1]

    elif direction == "down":
        if index >= len(items) - 1:
            return False

        items[index + 1], items[index] = items[index], items[index + 1]

    state["manual_queues"][bench_id] = items
    save_queue_control(state)

    return True


def set_manual_queues_from_board(board_data, added_by="planning_board"):
    if not isinstance(board_data, dict):
        raise ValueError("Planning board data must be a dictionary.")

    state = load_queue_control()

    clean_manual_queues = {}
    used_orders = set()

    for bench_id, items in board_data.items():
        bench_id = str(bench_id or "").strip()

        if not bench_id:
            continue

        if not isinstance(items, list):
            continue

        clean_items = []

        for raw_item in items:
            if isinstance(raw_item, dict):
                order_number = clean_order_number(raw_item.get("order_number", ""))
                note = str(raw_item.get("note", "")).strip()
            else:
                order_number = clean_order_number(raw_item)
                note = ""

            if not order_number:
                continue

            if order_number in used_orders:
                continue

            used_orders.add(order_number)

            clean_items.append({
                "order_number": order_number,
                "added_at": now_text(),
                "added_by": str(added_by or "planning_board").strip() or "planning_board",
                "note": note,
            })

        if clean_items:
            clean_manual_queues[bench_id] = clean_items

    state["manual_queues"] = clean_manual_queues

    for order_number in used_orders:
        remove_order_from_planning_pool_state(order_number, state)
        state.setdefault("held_orders", {})
        state["held_orders"].pop(order_number, None)

    save_queue_control(state)

    return state


def clear_manual_queues():
    state = load_queue_control()
    removed_count = sum(
        len(items)
        for items in state.get("manual_queues", {}).values()
    )

    state["manual_queues"] = {}

    save_queue_control(state)

    return removed_count


def add_held_order(
    order_number,
    bench_id="",
    reason="",
    note="",
    held_by="control",
    remove_from_manual_queues=True,
    remove_from_pool=True
):
    order_number = clean_order_number(order_number)
    bench_id = str(bench_id or "").strip()
    reason = str(reason or "").strip()
    note = str(note or "").strip()
    held_by = str(held_by or "control").strip() or "control"

    if not order_number:
        raise ValueError("Order number is required.")

    state = load_queue_control()

    if remove_from_manual_queues:
        remove_order_from_all_manual_queues(order_number, state)

    if remove_from_pool:
        remove_order_from_planning_pool_state(order_number, state)

    if not reason:
        reason = "On hold"

    state.setdefault("held_orders", {})
    state["held_orders"][order_number] = {
        "order_number": order_number,
        "bench_id": bench_id,
        "held_at": now_text(),
        "held_by": held_by,
        "reason": reason,
        "note": note,
    }

    save_queue_control(state)

    return state


def remove_held_order(order_number):
    order_number = clean_order_number(order_number)

    if not order_number:
        return None

    state = load_queue_control()

    removed = state.get("held_orders", {}).pop(order_number, None)

    save_queue_control(state)

    return removed


def release_held_order_to_queue(order_number, bench_id="", note="Released from hold"):
    order_number = clean_order_number(order_number)
    bench_id = str(bench_id or "").strip()

    if not order_number:
        raise ValueError("Order number is required.")

    state = load_queue_control()
    held_order = state.get("held_orders", {}).get(order_number)

    if held_order is None:
        raise ValueError("Order is not currently held.")

    if not bench_id:
        bench_id = str(held_order.get("bench_id", "")).strip()

    if not bench_id:
        raise ValueError("Bench ID is required to release this order to a queue.")

    state["held_orders"].pop(order_number, None)
    save_queue_control(state)

    add_order_to_manual_queue(
        bench_id=bench_id,
        order_number=order_number,
        note=note,
        added_by="release_hold",
        remove_from_other_queues=True,
        remove_from_pool=True
    )

    return held_order


def cleanup_queue_control(valid_order_numbers):
    valid_order_numbers = set(
        clean_order_number(order_number)
        for order_number in valid_order_numbers
        if clean_order_number(order_number)
    )

    if not valid_order_numbers:
        return []

    state = load_queue_control()
    removed = []

    clean_pool = []

    for item in state.get("planning_pool", []):
        order_number = clean_order_number(item.get("order_number", ""))

        if order_number in valid_order_numbers:
            clean_pool.append(item)
        else:
            removed.append({
                "type": "planning_pool",
                "bench_id": "",
                "order_number": order_number,
            })

    state["planning_pool"] = clean_pool

    for bench_id, items in list(state.get("manual_queues", {}).items()):
        clean_items = []

        for item in items:
            order_number = clean_order_number(item.get("order_number", ""))

            if order_number in valid_order_numbers:
                clean_items.append(item)
            else:
                removed.append({
                    "type": "manual_queue",
                    "bench_id": bench_id,
                    "order_number": order_number,
                })

        if clean_items:
            state["manual_queues"][bench_id] = clean_items
        else:
            state["manual_queues"].pop(bench_id, None)

    for order_number in list(state.get("held_orders", {}).keys()):
        if order_number not in valid_order_numbers:
            held_data = state["held_orders"].pop(order_number, {})

            removed.append({
                "type": "held_order",
                "bench_id": str(held_data.get("bench_id", "")).strip(),
                "order_number": order_number,
            })

    if removed:
        save_queue_control(state)

    return removed


def main():
    state = load_queue_control()

    print()
    print("===================================")
    print("LINEUP Queue Control")
    print("===================================")
    print(f"File           : {QUEUE_CONTROL_FILE}")
    print(f"Planning pool  : {len(state.get('planning_pool', []))}")
    print(f"Manual benches : {len(state.get('manual_queues', {}))}")
    print(f"Held orders    : {len(state.get('held_orders', {}))}")
    print()

    if state.get("planning_pool"):
        print("Planning Pool:")

        for index, item in enumerate(state.get("planning_pool", []), start=1):
            print(f"  {index}. {item.get('order_number', '')}")

    for bench_id, items in state.get("manual_queues", {}).items():
        print()
        print(f"{bench_id}:")

        for index, item in enumerate(items, start=1):
            print(
                f"  {index}. {item.get('order_number', '')} "
                f"{item.get('note', '')}"
            )

    if state.get("held_orders"):
        print()
        print("Held Orders:")

        for order_number, held_order in state.get("held_orders", {}).items():
            print(
                f"  {order_number}: "
                f"{held_order.get('reason', '')} "
                f"from {held_order.get('bench_id', '')}"
            )

    print()


if __name__ == "__main__":
    main()