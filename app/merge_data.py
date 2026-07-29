from pathlib import Path
import csv

from production_status import (
    is_ready_status,
    is_ready_for_production,
    production_state,
)

PROJECT_ROOT = Path(__file__).parent.parent

PRODUCTION_FILE = PROJECT_ROOT / "data" / "processed" / "production_list_clean.csv"
CAPACITY_SUMMARY_FILE = PROJECT_ROOT / "data" / "processed" / "capacities_order_summary.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "master_schedule.csv"

OUTPUT_COLUMNS = [
    "order_number",
    "material",
    "material_description",
    "scheduled_start",
    "scheduled_finish",
    "target_quantity",
    "confirmed_quantity",
    "customer",
    "priority",
    "is_released",
    "is_australia",
    "system_status",
    "user_status",

    # New production readiness fields
    "picked",
    "ready_for_production",
    "production_state",

    "scheduling_pool",
    "bench_work_centres",
    "bench_operations",
    "bench_remaining_minutes",
    "bench_operation_count",
]


def is_australia_customer(customer):
    customer_text = str(customer).strip().lower()
    return "yes" if "australia" in customer_text else "no"


production_by_order = {}

with open(
    PRODUCTION_FILE,
    "r",
    encoding="utf-8-sig",
    errors="ignore",
    newline="",
) as infile:

    reader = csv.DictReader(infile)

    for row in reader:
        production_by_order[row["order_number"].strip()] = row


rows_written = 0
missing_production_rows = 0

with open(
    CAPACITY_SUMMARY_FILE,
    "r",
    encoding="utf-8-sig",
    errors="ignore",
    newline="",
) as cap_file:

    capacity_reader = csv.DictReader(cap_file)

    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
        newline="",
    ) as outfile:

        writer = csv.writer(outfile)
        writer.writerow(OUTPUT_COLUMNS)

        for capacity_row in capacity_reader:

            order_number = capacity_row["order_number"].strip()

            production_row = production_by_order.get(order_number)

            if production_row is None:
                missing_production_rows += 1
                continue

            priority = production_row["priority"].strip()

            if priority == "":
                priority = "0"

            system_status = production_row["system_status"].strip()

            status_tokens = system_status.split()

            is_released = "yes" if "REL" in status_tokens else "no"

            customer = production_row["customer"].strip()

            is_australia = is_australia_customer(customer)

            #
            # Build a combined order dictionary for the
            # production readiness engine.
            #

            order = {
                **production_row,
                **capacity_row,
                "system_status": system_status,
                "user_status": production_row["user_status"].strip(),
                "is_released": is_released,
            }

            picked = "yes" if is_ready_status(order) else "no"

            ready = "yes" if is_ready_for_production(order) else "no"

            state = production_state(order)

            writer.writerow([
                order_number,
                production_row["material"],
                production_row["material_description"],
                production_row["scheduled_start"],
                production_row["scheduled_finish"],
                production_row["target_quantity"],
                production_row["confirmed_quantity"],
                customer,
                priority,
                is_released,
                is_australia,
                system_status,
                production_row["user_status"],

                picked,
                ready,
                state,

                capacity_row["scheduling_pool"],
                capacity_row["bench_work_centres"],
                capacity_row["bench_operations"],
                capacity_row["bench_remaining_minutes"],
                capacity_row["bench_operation_count"],
            ])

            rows_written += 1

print()
print("===================================")
print("LINEUP Merge Complete")
print("===================================")
print(f"Production input : {PRODUCTION_FILE.name}")
print(f"Capacity input   : {CAPACITY_SUMMARY_FILE.name}")
print(f"Output           : {OUTPUT_FILE.name}")
print(f"Rows             : {rows_written}")
print(f"Missing metadata : {missing_production_rows}")
print()