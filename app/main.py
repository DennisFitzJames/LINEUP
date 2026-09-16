print("LINEUP")
print("Starting capacity parser...")
print()

import parse_capacities
import parse_production_list
import summarise_capacities
import merge_data

from overrides import prune_terminal_manual_splits

removed_splits = prune_terminal_manual_splits()
if removed_splits:
    print()
    print("Removed completed manual order splits:")
    for order_number, reason in sorted(removed_splits.items()):
        print(f"  {order_number}: {reason}")

import schedule_orders
import build_dashboard
import schedule_report
import split_reccomendations
print()
print("Refreshing BW logistics browser data...")
from logistics.refresh import refresh_logistics
refresh_logistics(force=True)
print("BW logistics browser data refreshed.")
