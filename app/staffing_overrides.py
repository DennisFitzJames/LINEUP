from pathlib import Path

import json

from datetime import datetime
 
PROJECT_ROOT = Path(__file__).parent.parent

STAFFING_FILE = PROJECT_ROOT / "config" / "staffing_overrides.json"
 
DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
 
 
def now_text():

    return datetime.now().strftime(DATE_TIME_FORMAT)
 
 
def parse_int(value, default=0):

    try:

        text = str(value or "").strip()
 
        if not text:

            return default
 
        return int(float(text))
 
    except (TypeError, ValueError):

        return default
 
 
def default_staffing_state():

    return {

        "version": 1,

        "benches": {},

        "updated_at": "",

    }
 
 
def normalise_staffing_state(data):

    state = default_staffing_state()
 
    if isinstance(data, dict):

        state.update(data)
 
    state["version"] = 1
 
    if not isinstance(state.get("benches"), dict):

        state["benches"] = {}
 
    clean_benches = {}
 
    for bench_id, override in state["benches"].items():

        bench_id = str(bench_id or "").strip()
 
        if not bench_id or not isinstance(override, dict):

            continue
 
        people = parse_int(override.get("people", 0), 0)
 
        if people <= 0:

            continue
 
        clean_benches[bench_id] = {

            "people": people,

            "updated_at": str(override.get("updated_at", "") or "").strip(),

            "updated_by": (

                str(override.get("updated_by", "control") or "").strip()

                or "control"

            ),

            "note": str(override.get("note", "") or "").strip(),

        }
 
    state["benches"] = clean_benches
 
    return state
 
 
def load_staffing_overrides():

    if not STAFFING_FILE.exists():

        state = default_staffing_state()

        save_staffing_overrides(state)

        return state
 
    try:

        with open(STAFFING_FILE, "r", encoding="utf-8") as infile:

            data = json.load(infile)
 
    except (json.JSONDecodeError, OSError):

        state = default_staffing_state()

        save_staffing_overrides(state)

        return state
 
    return normalise_staffing_state(data)
 
 
def save_staffing_overrides(state):

    STAFFING_FILE.parent.mkdir(parents=True, exist_ok=True)
 
    state = normalise_staffing_state(state)

    state["updated_at"] = now_text()
 
    with open(STAFFING_FILE, "w", encoding="utf-8") as outfile:

        json.dump(state, outfile, indent=4)
 
 
def get_staffing_override(bench_id, state=None):

    bench_id = str(bench_id or "").strip()
 
    if not bench_id:

        return None
 
    if state is None:

        state = load_staffing_overrides()
 
    return state.get("benches", {}).get(bench_id)
 
 
def set_staffing_override(

    bench_id,

    people,

    note="",

    updated_by="control"

):

    bench_id = str(bench_id or "").strip()

    people = parse_int(people, 0)
 
    if not bench_id:

        raise ValueError("Bench ID is required.")
 
    if people <= 0:

        raise ValueError("People must be greater than zero.")
 
    state = load_staffing_overrides()
 
    state.setdefault("benches", {})

    state["benches"][bench_id] = {

        "people": people,

        "updated_at": now_text(),

        "updated_by": (

            str(updated_by or "control").strip()

            or "control"

        ),

        "note": str(note or "").strip(),

    }
 
    save_staffing_overrides(state)
 
    return state["benches"][bench_id]
 
 
def clear_staffing_override(bench_id):

    bench_id = str(bench_id or "").strip()
 
    if not bench_id:

        return None
 
    state = load_staffing_overrides()

    removed = state.get("benches", {}).pop(bench_id, None)
 
    save_staffing_overrides(state)
 
    return removed
 
 
def clear_all_staffing_overrides():

    state = load_staffing_overrides()

    removed_count = len(state.get("benches", {}))
 
    state["benches"] = {}

    save_staffing_overrides(state)
 
    return removed_count
 
 
def staffing_factor_for_bench(

    bench_id,

    baseline_people,

    state=None

):

    """

    Returns a duration multiplier.
 
    No explicit override:

        factor = 1.0

        SAP remaining capacity is used unchanged.
 
    Example explicit override:

        SAP baseline people = 2

        Manual people = 1

        factor = 2 / 1 = 2.0

    """

    baseline_people = parse_int(baseline_people, 1)
 
    if baseline_people <= 0:

        baseline_people = 1
 
    override = get_staffing_override(bench_id, state=state)
 
    if not override:

        return 1.0
 
    actual_people = parse_int(override.get("people", 0), 0)
 
    if actual_people <= 0:

        return 1.0
 
    return baseline_people / actual_people
 
 
def effective_minutes(

    base_minutes,

    bench_id,

    baseline_people,

    state=None

):

    base_minutes = parse_int(base_minutes, 0)
 
    if base_minutes <= 0:

        return 0
 
    factor = staffing_factor_for_bench(

        bench_id=bench_id,

        baseline_people=baseline_people,

        state=state

    )
 
    return max(1, round(base_minutes * factor))
 
 
if __name__ == "__main__":

    state = load_staffing_overrides()
 
    print()

    print("===================================")

    print("LINEUP Staffing Overrides")

    print("===================================")

    print(f"File      : {STAFFING_FILE}")

    print(f"Overrides : {len(state.get('benches', {}))}")

    print()
 
    for bench_id, override in state.get("benches", {}).items():

        print(

            f"{bench_id}: "

            f"{override.get('people')} people "

            f"{override.get('note', '')}"

        )
 
    print()