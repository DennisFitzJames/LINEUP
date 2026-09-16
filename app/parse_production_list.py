from pathlib import Path
import csv

PROJECT_ROOT = Path(__file__).parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "COOIS_ProductionList_Latest.txt"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "production_list_clean.csv"

OUTPUT_COLUMNS = [
    "order_number",
    "material",
    "material_description",
    "scheduled_start",
    "scheduled_finish",
    "actual_start",
    "actual_finish",
    "target_quantity",
    "confirmed_quantity",
    "customer",
    "priority",
    "system_status",
    "user_status",
]

rows_written = 0
parsed_rows = []

with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as infile:
    for line in infile:
        line = line.strip()

        if not line.startswith("|"):
            continue

        parts = [part.strip() for part in line.split("|")[1:-1]]

        if not parts or parts[0] == "SchedStart":
            continue

        if len(parts) != 13:
            continue

        try:
            scheduled_start = parts[0]
            scheduled_finish = parts[1]
            actual_start = parts[2]
            actual_finish = parts[3]

            order_number = str(parts[4]).strip()
            material = parts[5]
            material_description = parts[6]
            target_quantity = parts[7]
            confirmed_quantity = parts[8]
            customer = parts[9]
            priority = parts[10]
            system_status = parts[11]
            user_status = parts[12]

            parsed_rows.append([
                order_number,
                material,
                material_description,
                scheduled_start,
                scheduled_finish,
                actual_start,
                actual_finish,
                target_quantity,
                confirmed_quantity,
                customer,
                priority,
                system_status,
                user_status,
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
print("LINEUP Production Parser Complete")
print("===================================")
print(f"Input : {INPUT_FILE.name}")
print(f"Output: {OUTPUT_FILE.name}")
print(f"Rows  : {rows_written}")
print()
