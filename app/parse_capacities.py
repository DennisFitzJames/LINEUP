from pathlib import Path
import csv

PROJECT_ROOT = Path(__file__).parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "COOIS_Capacities_Latest.txt"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "capacities_clean.csv"

OUTPUT_COLUMNS = [
    "order_number",
    "operation",
    "capacity_category",
    "work_centre",
    "target_process_hours",
    "remaining_process_hours",
    "target_setup_hours",
    "remaining_setup_hours",
    "target_teardown_hours",
    "remaining_teardown_hours",
    "remaining_total_hours",
    "remaining_total_minutes",
    "earliest_start",
    "latest_finish",
    "operation_description",
    "actual_start",
    "actual_finish",
]


def to_float(value):
    text = str(value or "").strip().replace(",", "")
    if text == "":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def combine_date_time(date_text, time_text):
    date_value = str(date_text or "").strip()
    time_value = str(time_text or "").strip()
    if not date_value:
        return ""
    return f"{date_value} {time_value}".strip()


rows_written = 0
parsed_rows = []

with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as infile:
    for line in infile:
        line = line.strip()

        if not line.startswith("|"):
            continue

        parts = [part.strip() for part in line.split("|")[1:-1]]

        if not parts or parts[0] == "Order":
            continue

        if len(parts) != 19:
            continue

        try:
            order_number = str(parts[0]).strip()
            operation = str(parts[1]).strip()
            capacity_category = str(parts[2]).strip()
            work_centre = str(parts[3]).strip()

            target_process = to_float(parts[4])
            remaining_process = to_float(parts[5])
            target_setup = to_float(parts[6])
            remaining_setup = to_float(parts[7])
            target_teardown = to_float(parts[8])
            remaining_teardown = to_float(parts[9])

            remaining_total = (
                remaining_process
                + remaining_setup
                + remaining_teardown
            )

            remaining_minutes = round(remaining_total * 60)

            earliest_start = combine_date_time(parts[10], parts[11])
            latest_finish = combine_date_time(parts[12], parts[13])
            operation_description = parts[14]
            actual_start = combine_date_time(parts[15], parts[16])
            actual_finish = combine_date_time(parts[17], parts[18])

            parsed_rows.append([
                order_number,
                operation,
                capacity_category,
                work_centre,
                target_process,
                remaining_process,
                target_setup,
                remaining_setup,
                target_teardown,
                remaining_teardown,
                round(remaining_total, 3),
                remaining_minutes,
                earliest_start,
                latest_finish,
                operation_description,
                actual_start,
                actual_finish,
            ])
        except Exception as error:
            print(f"Skipped row: {error}")

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as outfile:
    writer = csv.writer(outfile)
    writer.writerow(OUTPUT_COLUMNS)

    for row in parsed_rows:
        writer.writerow(row)
        rows_written += 1

print()
print("===================================")
print("LINEUP Capacity Parser Complete")
print("===================================")
print(f"Input : {INPUT_FILE.name}")
print(f"Output: {OUTPUT_FILE.name}")
print(f"Rows  : {rows_written}")
print()
