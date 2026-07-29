from pathlib import Path
import csv
from datetime import datetime

# --------------------------------------------------
# FILE LOCATIONS
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "COOIS_Capacities_Latest.txt"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "capacities_clean.csv"

# --------------------------------------------------
# OUTPUT COLUMNS
# --------------------------------------------------

OUTPUT_COLUMNS = [
    "order_number",
    "operation",
    "work_centre",
    "remaining_process_hours",
    "remaining_setup_hours",
    "remaining_teardown_hours",
    "remaining_total_hours",
    "remaining_total_minutes",
    "earliest_start",
    "latest_finish",
    "operation_description"
]

# --------------------------------------------------
# MAIN PARSER
# --------------------------------------------------

rows_written = 0

with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as infile:

    parsed_rows = []

    for line in infile:

        line = line.strip()

        # Ignore headers and separators
        if not line.startswith("|"):
            continue

        # Split pipe-delimited row
        parts = [p.strip() for p in line.split("|")[1:-1]]

        # Ignore header row
        if len(parts) > 0 and parts[0] == "Order":
            continue

        # Expected COOIS capacity export row length
        if len(parts) != 19:
            continue

        try:

            order_number = parts[0]
            operation = parts[1]
            work_centre = parts[3]

            remaining_process = float(parts[5] or 0)
            remaining_setup = float(parts[7] or 0)
            remaining_teardown = float(parts[9] or 0)

            total_remaining = (
                remaining_process
                + remaining_setup
                + remaining_teardown
            )

            total_minutes = round(total_remaining * 60)

            earliest_start = (
                parts[10] + " " + parts[11]
            ).strip()

            latest_finish = (
                parts[12] + " " + parts[13]
            ).strip()

            operation_description = parts[14]

            parsed_rows.append([
                order_number,
                operation,
                work_centre,
                remaining_process,
                remaining_setup,
                remaining_teardown,
                round(total_remaining, 3),
                total_minutes,
                earliest_start,
                latest_finish,
                operation_description
            ])

        except Exception as e:

            print(f"Skipped row: {e}")

# --------------------------------------------------
# WRITE CSV
# --------------------------------------------------

OUTPUT_FILE.parent.mkdir(exist_ok=True)

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as outfile:

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