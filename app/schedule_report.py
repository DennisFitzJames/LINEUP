from pathlib import Path
import csv
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent

SCHEDULED_FILE = PROJECT_ROOT / "data" / "processed" / "scheduled_orders.csv"
OVERFLOW_FILE = PROJECT_ROOT / "data" / "processed" / "overflow_orders.csv"
BENCHES_FILE = PROJECT_ROOT / "config" / "benches.csv"

BENCH_UTILISATION_FILE = PROJECT_ROOT / "data" / "processed" / "bench_utilisation.csv"
SCHEDULE_SUMMARY_FILE = PROJECT_ROOT / "data" / "processed" / "schedule_summary.csv"

FULL_BENCH_MINUTES = 475


def read_csv(path):
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as infile:
        return list(csv.DictReader(infile))


def parse_int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return default


def parse_float(value, default=0.0):
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def load_open_benches():
    rows = read_csv(BENCHES_FILE)

    benches = {}

    for row in rows:
        if row["is_open"].strip().lower() != "yes":
            continue

        bench_id = row["bench_id"].strip()
        efficiency = parse_float(row["efficiency"], 0.0)
        available_minutes = round(FULL_BENCH_MINUTES * efficiency)

        benches[bench_id] = {
            "bench_id": bench_id,
            "bench_name": row["bench_name"].strip(),
            "scheduling_pool": row["scheduling_pool"].strip(),
            "standard_people": row["standard_people"].strip(),
            "actual_people": row["actual_people"].strip(),
            "efficiency": row["efficiency"].strip(),
            "available_minutes": available_minutes,
            "orders": [],
        }

    return benches


def build_bench_utilisation(benches, scheduled_rows):
    for row in scheduled_rows:
        bench_id = row["bench_id"].strip()

        if bench_id not in benches:
            benches[bench_id] = {
                "bench_id": bench_id,
                "bench_name": row["bench_name"].strip(),
                "scheduling_pool": row["scheduling_pool"].strip(),
                "standard_people": "",
                "actual_people": "",
                "efficiency": "",
                "available_minutes": 0,
                "orders": [],
            }

        benches[bench_id]["orders"].append(row)

    utilisation_rows = []

    for bench_id in sorted(benches.keys()):
        bench = benches[bench_id]
        orders = sorted(
            bench["orders"],
            key=lambda r: parse_int(r.get("sequence", 0), 0)
        )

        used_minutes = sum(
            parse_int(order.get("bench_remaining_minutes", 0), 0)
            for order in orders
        )

        available_minutes = bench["available_minutes"]
        remaining_minutes = available_minutes - used_minutes

        if available_minutes > 0:
            utilisation_percent = round((used_minutes / available_minutes) * 100, 1)
        else:
            utilisation_percent = 0

        priority_orders = sum(
            1 for order in orders
            if parse_int(order.get("priority", 0), 0) > 0
        )

        australia_orders = sum(
            1 for order in orders
            if order.get("is_australia", "").strip().lower() == "yes"
        )

        consecutive_same_material = 0
        previous_material = ""

        for order in orders:
            material = order.get("material", "").strip()

            if previous_material and material == previous_material:
                consecutive_same_material += 1

            previous_material = material

        utilisation_rows.append({
            "bench_id": bench["bench_id"],
            "bench_name": bench["bench_name"],
            "scheduling_pool": bench["scheduling_pool"],
            "available_minutes": available_minutes,
            "used_minutes": used_minutes,
            "remaining_minutes": remaining_minutes,
            "utilisation_percent": utilisation_percent,
            "order_count": len(orders),
            "priority_order_count": priority_orders,
            "australia_order_count": australia_orders,
            "consecutive_same_material_count": consecutive_same_material,
        })

    return utilisation_rows


def build_schedule_summary(scheduled_rows, overflow_rows, utilisation_rows):
    scheduled_orders = len(scheduled_rows)
    overflow_orders = len(overflow_rows)

    scheduled_minutes = sum(
        parse_int(row.get("bench_remaining_minutes", 0), 0)
        for row in scheduled_rows
    )

    overflow_minutes = sum(
        parse_int(row.get("bench_remaining_minutes", 0), 0)
        for row in overflow_rows
    )

    priority_scheduled = sum(
        1 for row in scheduled_rows
        if parse_int(row.get("priority", 0), 0) > 0
    )

    priority_overflow = sum(
        1 for row in overflow_rows
        if parse_int(row.get("priority", 0), 0) > 0
    )

    australia_scheduled = sum(
        1 for row in scheduled_rows
        if row.get("is_australia", "").strip().lower() == "yes"
    )

    australia_overflow = sum(
        1 for row in overflow_rows
        if row.get("is_australia", "").strip().lower() == "yes"
    )

    open_benches = len(utilisation_rows)

    total_available_minutes = sum(
        parse_int(row["available_minutes"], 0)
        for row in utilisation_rows
    )

    total_used_minutes = sum(
        parse_int(row["used_minutes"], 0)
        for row in utilisation_rows
    )

    total_remaining_minutes = sum(
        parse_int(row["remaining_minutes"], 0)
        for row in utilisation_rows
    )

    if total_available_minutes > 0:
        overall_utilisation_percent = round(
            (total_used_minutes / total_available_minutes) * 100,
            1
        )
    else:
        overall_utilisation_percent = 0

    same_material_runs = sum(
        parse_int(row["consecutive_same_material_count"], 0)
        for row in utilisation_rows
    )

    summary_rows = [
        ["open_benches", open_benches],
        ["scheduled_orders", scheduled_orders],
        ["overflow_orders", overflow_orders],
        ["scheduled_minutes", scheduled_minutes],
        ["overflow_minutes", overflow_minutes],
        ["total_available_minutes", total_available_minutes],
        ["total_used_minutes", total_used_minutes],
        ["total_remaining_minutes", total_remaining_minutes],
        ["overall_utilisation_percent", overall_utilisation_percent],
        ["priority_orders_scheduled", priority_scheduled],
        ["priority_orders_overflow", priority_overflow],
        ["australia_orders_scheduled", australia_scheduled],
        ["australia_orders_overflow", australia_overflow],
        ["consecutive_same_material_runs", same_material_runs],
    ]

    return summary_rows


def write_bench_utilisation(utilisation_rows):
    columns = [
        "bench_id",
        "bench_name",
        "scheduling_pool",
        "available_minutes",
        "used_minutes",
        "remaining_minutes",
        "utilisation_percent",
        "order_count",
        "priority_order_count",
        "australia_order_count",
        "consecutive_same_material_count",
    ]

    BENCH_UTILISATION_FILE.parent.mkdir(exist_ok=True)

    with open(BENCH_UTILISATION_FILE, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=columns)
        writer.writeheader()

        for row in utilisation_rows:
            writer.writerow(row)


def write_schedule_summary(summary_rows):
    SCHEDULE_SUMMARY_FILE.parent.mkdir(exist_ok=True)

    with open(SCHEDULE_SUMMARY_FILE, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(["metric", "value"])

        for row in summary_rows:
            writer.writerow(row)


scheduled_rows = read_csv(SCHEDULED_FILE) 
overflow_rows = read_csv(OVERFLOW_FILE)

benches = load_open_benches()

utilisation_rows = build_bench_utilisation(benches, scheduled_rows) 
summary_rows = build_schedule_summary(scheduled_rows, overflow_rows, utilisation_rows)

write_bench_utilisation(utilisation_rows)
write_schedule_summary(summary_rows)

print()
print("===================================")
print("LINEUP Schedule Report Complete")
print("===================================")
print(f"Bench utilisation: {BENCH_UTILISATION_FILE.name}") 
print(f"Schedule summary : {SCHEDULE_SUMMARY_FILE.name}")
print()