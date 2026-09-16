from pathlib import Path
import csv

PROJECT_ROOT = Path(__file__).parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "capacities_clean.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "capacities_order_summary.csv"

# Work centres that belong to this LINEUP trial area 

BENCH_WORK_CENTRES = {"CSKI-1", "MVKI-1", "LVPA-2", "LVPA-5"}

WORK_CENTRE_TO_POOL = {
    "CSKI-1": "CSKI_MVKI",
    "MVKI-1": "CSKI_MVKI",
    "LVPA-2": "LVPA",
    "LVPA-5": "LVPA",
}

OUTPUT_COLUMNS = [
    "order_number",
    "scheduling_pool",
    "bench_work_centres",
    "bench_operations",
    "bench_remaining_minutes",
    "bench_operation_count"
]

orders = {}

with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore", newline="") as infile:
    reader = csv.DictReader(infile)

    for row in reader:
        order_number = row["order_number"].strip()
        work_centre = row["work_centre"].strip()
        operation = row["operation"].strip()

        if work_centre not in BENCH_WORK_CENTRES:
            continue

        try:
            remaining_minutes = int(float(row["remaining_total_minutes"]))
        except ValueError:
            remaining_minutes = 0

        if order_number not in orders:
            orders[order_number] = {
                "pools": set(),
                "work_centres": set(),
                "operations": [],
                "remaining_minutes": 0,
                "operation_count": 0
            }

        orders[order_number]["pools"].add(WORK_CENTRE_TO_POOL[work_centre])
        orders[order_number]["work_centres"].add(work_centre)
        orders[order_number]["operations"].append(operation)
        orders[order_number]["remaining_minutes"] += remaining_minutes
        orders[order_number]["operation_count"] += 1

OUTPUT_FILE.parent.mkdir(exist_ok=True)

with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as outfile:
    writer = csv.writer(outfile)
    writer.writerow(OUTPUT_COLUMNS)

    rows_written = 0

    for order_number, data in sorted(orders.items()):
        scheduling_pool = " / ".join(sorted(data["pools"]))

        writer.writerow([
            order_number,
            scheduling_pool,
            " / ".join(sorted(data["work_centres"])),
            " → ".join(data["operations"]),
            data["remaining_minutes"],
            data["operation_count"]
        ])

        rows_written += 1

print()
print("===================================")
print("LINEUP Capacity Summary Complete")
print("===================================")
print(f"Input : {INPUT_FILE.name}")
print(f"Output: {OUTPUT_FILE.name}")
print(f"Rows  : {rows_written}")
print()