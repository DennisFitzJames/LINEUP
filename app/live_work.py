from pathlib import Path

import json

from datetime import datetime
 
from working_calendar import working_minutes_between
 
PROJECT_ROOT = Path(__file__).parent.parent

LIVE_WORK_FILE = PROJECT_ROOT / "data" / "processed" / "live_work_state.json"
 
DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
 
 
def now_text():

    return datetime.now().strftime(DATE_TIME_FORMAT)
 
 
def parse_datetime(value):

    if isinstance(value, datetime):

        return value
 
    value = str(value or "").strip()
 
    if not value:

        return None
 
    for fmt in (

        DATE_TIME_FORMAT,

        "%Y-%m-%d %H:%M",

        "%d/%m/%Y %H:%M",

        "%d.%m.%Y %H:%M:%S",

        "%d.%m.%Y %H:%M",

    ):

        try:

            return datetime.strptime(value, fmt)

        except ValueError:

            pass
 
    return None
 
 
def parse_int(value, default=0):

    try:

        text = str(value or "").strip()
 
        if not text:

            return default
 
        return int(float(text))
 
    except (TypeError, ValueError):

        return default
 
 
def default_live_work_state():

    return {

        "version": 2,

        "benches": {},

        "updated_at": "",

    }
 
 
def normalise_bench_state(bench_state):

    if not isinstance(bench_state, dict):

        return None
 
    order_number = str(

        bench_state.get("active_order_number", "") or ""

    ).strip()
 
    if not order_number:

        return None
 
    return {

        "active_order_number": order_number,

        "started_at": str(

            bench_state.get("started_at", "") or ""

        ).strip(),

        "started_remaining_minutes": parse_int(

            bench_state.get("started_remaining_minutes", 0),

            0

        ),

        "last_known_material": str(

            bench_state.get("last_known_material", "") or ""

        ).strip(),

        "last_known_description": str(

            bench_state.get("last_known_description", "") or ""

        ).strip(),

        "last_known_scheduling_pool": str(

            bench_state.get("last_known_scheduling_pool", "") or ""

        ).strip(),

        "started_by": (

            str(bench_state.get("started_by", "dashboard") or "").strip()

            or "dashboard"

        ),

        "latest_sap_remaining_minutes": parse_int(

            bench_state.get("latest_sap_remaining_minutes", 0),

            0

        ),

        "latest_effective_remaining_minutes": parse_int(

            bench_state.get("latest_effective_remaining_minutes", 0),

            0

        ),

        "latest_sap_refresh_at": str(

            bench_state.get("latest_sap_refresh_at", "") or ""

        ).strip(),

        "latest_staffing_factor": str(

            bench_state.get("latest_staffing_factor", "1.0") or "1.0"

        ).strip(),

    }
 
 
def read_live_work_state():

    if not LIVE_WORK_FILE.exists():

        return default_live_work_state()
 
    try:

        with open(LIVE_WORK_FILE, "r", encoding="utf-8") as infile:

            data = json.load(infile)
 
    except (json.JSONDecodeError, OSError):

        return default_live_work_state()
 
    state = default_live_work_state()
 
    if isinstance(data, dict):

        state.update(data)
 
    state["version"] = 2
 
    if not isinstance(state.get("benches"), dict):

        state["benches"] = {}
 
    clean_benches = {}
 
    for bench_id, bench_state in state["benches"].items():

        bench_id = str(bench_id or "").strip()
 
        if not bench_id:

            continue
 
        clean_state = normalise_bench_state(bench_state)
 
        if clean_state:

            clean_benches[bench_id] = clean_state
 
    state["benches"] = clean_benches
 
    return state
 
 
def write_live_work_state(state):

    LIVE_WORK_FILE.parent.mkdir(parents=True, exist_ok=True)
 
    if not isinstance(state, dict):

        state = default_live_work_state()
 
    state["version"] = 2
 
    if not isinstance(state.get("benches"), dict):

        state["benches"] = {}
 
    state["updated_at"] = now_text()
 
    with open(LIVE_WORK_FILE, "w", encoding="utf-8") as outfile:

        json.dump(state, outfile, indent=4)
 
 
def get_bench_live_state(bench_id):

    bench_id = str(bench_id or "").strip()
 
    if not bench_id:

        return None
 
    state = read_live_work_state()
 
    return state.get("benches", {}).get(bench_id)
 
 
def get_active_benches():

    state = read_live_work_state()
 
    return state.get("benches", {})
 
 
def build_bench_state_from_order(

    order,

    started_by="dashboard",

    started_at_text=""

):

    order_number = str(

        order.get("order_number", "") or ""

    ).strip()
 
    if not order_number:

        raise ValueError(

            "Cannot start live work: order number is missing."

        )
 
    started_remaining_minutes = parse_int(

        order.get("bench_remaining_minutes", 0),

        0

    )
 
    if started_remaining_minutes <= 0:

        raise ValueError(

            "Cannot start live work: remaining minutes are missing."

        )
 
    started_at_text = str(started_at_text or "").strip()
 
    if started_at_text:

        started_at = parse_datetime(started_at_text)
 
        if started_at is None:

            raise ValueError(

                "Cannot start live work: start time is invalid."

            )
 
        final_started_at = started_at.strftime(DATE_TIME_FORMAT)

    else:

        final_started_at = now_text()
 
    return {

        "active_order_number": order_number,

        "started_at": final_started_at,

        "started_remaining_minutes": started_remaining_minutes,

        "last_known_material": str(

            order.get("material", "") or ""

        ).strip(),

        "last_known_description": str(

            order.get("material_description", "") or ""

        ).strip(),

        "last_known_scheduling_pool": str(

            order.get("scheduling_pool", "") or ""

        ).strip(),

        "started_by": (

            str(started_by or "dashboard").strip()

            or "dashboard"

        ),

        "latest_sap_remaining_minutes": 0,

        "latest_effective_remaining_minutes": 0,

        "latest_sap_refresh_at": "",

        "latest_staffing_factor": "1.0",

    }
 
 
def start_order_on_bench(

    bench_id,

    order,

    started_by="dashboard",

    started_at_text=""

):

    bench_id = str(bench_id or "").strip()
 
    if not bench_id:

        raise ValueError(

            "Cannot start live work: bench ID is missing."

        )
 
    state = read_live_work_state()

    previous_bench_state = state["benches"].get(bench_id)
 
    new_bench_state = build_bench_state_from_order(

        order,

        started_by=started_by,

        started_at_text=started_at_text

    )
 
    state["benches"][bench_id] = new_bench_state

    write_live_work_state(state)
 
    return previous_bench_state, new_bench_state
 
 
def stop_order_on_bench(

    bench_id,

    expected_order_number=""

):

    bench_id = str(bench_id or "").strip()

    expected_order_number = str(

        expected_order_number or ""

    ).strip()
 
    if not bench_id:

        raise ValueError(

            "Cannot stop live work: bench ID is missing."

        )
 
    state = read_live_work_state()

    previous_bench_state = state["benches"].get(bench_id)
 
    if previous_bench_state and expected_order_number:

        active_order_number = str(

            previous_bench_state.get(

                "active_order_number",

                ""

            )

        ).strip()
 
        if (

            active_order_number

            and active_order_number != expected_order_number

        ):

            raise ValueError(

                f"Cannot stop live work: bench {bench_id} "

                f"is working on order {active_order_number}, "

                f"not {expected_order_number}."

            )
 
    if bench_id in state["benches"]:

        del state["benches"][bench_id]
 
    write_live_work_state(state)
 
    return previous_bench_state
 
 
def clear_all_live_work():

    state = read_live_work_state()

    removed_count = len(state.get("benches", {}))
 
    state["benches"] = {}

    write_live_work_state(state)
 
    return removed_count
 
 
def choose_live_elapsed_start(

    started_at,

    sap_refresh_at

):

    """

    SAP remaining already includes confirmations up to its refresh time.
 
    Therefore LINEUP only subtracts elapsed working time after the newer

    of:

        - the live tracking start

        - the latest SAP refresh

    """

    valid_values = [

        value

        for value in (started_at, sap_refresh_at)

        if value is not None

    ]
 
    if not valid_values:

        return None
 
    return max(valid_values)
 
 
def apply_live_state_to_order(

    order,

    bench_state,

    sap_refresh_at=None,

    staffing_factor=1.0

):

    live_order = dict(order)
 
    started_at = parse_datetime(

        bench_state.get("started_at", "")

    )

    sap_refresh_at = parse_datetime(sap_refresh_at)
 
    sap_remaining_minutes = parse_int(

        order.get("bench_remaining_minutes", 0),

        0

    )
 
    try:

        staffing_factor = float(staffing_factor)

    except (TypeError, ValueError):

        staffing_factor = 1.0
 
    if staffing_factor <= 0:

        staffing_factor = 1.0
 
    effective_snapshot_minutes = max(

        0,

        round(sap_remaining_minutes * staffing_factor)

    )
 
    elapsed_start = choose_live_elapsed_start(

        started_at,

        sap_refresh_at

    )
 
    elapsed_minutes = working_minutes_between(

        elapsed_start,

        datetime.now()

    )
 
    remaining_minutes = max(

        0,

        effective_snapshot_minutes - elapsed_minutes

    )
 
    live_order["bench_remaining_minutes"] = remaining_minutes

    live_order["live_active"] = "yes"

    live_order["live_started_at"] = (

        bench_state.get("started_at", "")

    )

    live_order["live_started_remaining_minutes"] = (

        effective_snapshot_minutes

    )

    live_order["live_elapsed_minutes"] = elapsed_minutes

    live_order["live_sap_remaining_minutes"] = (

        sap_remaining_minutes

    )

    live_order["live_sap_refresh_at"] = (

        sap_refresh_at.strftime(DATE_TIME_FORMAT)

        if sap_refresh_at

        else ""

    )

    live_order["live_staffing_factor"] = (

        f"{staffing_factor:.4f}"

    )
 
    if not live_order.get("material"):

        live_order["material"] = bench_state.get(

            "last_known_material",

            ""

        )
 
    if not live_order.get("material_description"):

        live_order["material_description"] = bench_state.get(

            "last_known_description",

            ""

        )
 
    if not live_order.get("scheduling_pool"):

        live_order["scheduling_pool"] = bench_state.get(

            "last_known_scheduling_pool",

            ""

        )
 
    return live_order
 
 
def update_live_snapshot(

    bench_id,

    sap_remaining_minutes,

    effective_remaining_minutes,

    sap_refresh_at,

    staffing_factor

):

    bench_id = str(bench_id or "").strip()
 
    if not bench_id:

        return
 
    state = read_live_work_state()

    bench_state = state.get("benches", {}).get(bench_id)
 
    if not bench_state:

        return
 
    sap_refresh_at = parse_datetime(sap_refresh_at)
 
    bench_state["latest_sap_remaining_minutes"] = parse_int(

        sap_remaining_minutes,

        0

    )

    bench_state["latest_effective_remaining_minutes"] = parse_int(

        effective_remaining_minutes,

        0

    )

    bench_state["latest_sap_refresh_at"] = (

        sap_refresh_at.strftime(DATE_TIME_FORMAT)

        if sap_refresh_at

        else ""

    )

    bench_state["latest_staffing_factor"] = str(

        staffing_factor

    )
 
    state["benches"][bench_id] = bench_state

    write_live_work_state(state)
 
 
def cleanup_live_work_for_missing_orders(

    valid_order_numbers

):

    valid_order_numbers = {

        str(value).strip()

        for value in valid_order_numbers

        if str(value).strip()

    }
 
    state = read_live_work_state()

    removed = []
 
    for bench_id, bench_state in list(

        state.get("benches", {}).items()

    ):

        order_number = str(

            bench_state.get(

                "active_order_number",

                ""

            )

        ).strip()
 
        if order_number not in valid_order_numbers:

            removed.append({

                "bench_id": bench_id,

                "order_number": order_number,

            })
 
            del state["benches"][bench_id]
 
    if removed:

        write_live_work_state(state)
 
    return removed
 
 
if __name__ == "__main__":

    state = read_live_work_state()
 
    print()

    print("===================================")

    print("LINEUP Live Work")

    print("===================================")

    print(f"File       : {LIVE_WORK_FILE}")

    print(f"Benches    : {len(state.get('benches', {}))}")

    print(f"Updated at : {state.get('updated_at', '')}")

    print()