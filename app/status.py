from pathlib import Path
import json
import sys
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent

STATUS_FILE = PROJECT_ROOT / "data" / "processed" / "lineup_status.json"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_status():
    return {
        "last_run_status": "unknown",
        "last_successful_run": "",
        "last_attempted_run": "",
        "failure_step": "",
        "failure_message": "",
    }


def read_status():
    if not STATUS_FILE.exists():
        return default_status()

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as infile:
            data = json.load(infile)

    except (json.JSONDecodeError, OSError):
        return default_status()

    status = default_status()
    status.update(data)

    return status


def write_status(data):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

    status = default_status()
    status.update(data)

    with open(STATUS_FILE, "w", encoding="utf-8") as outfile:
        json.dump(status, outfile, indent=4)


def mark_attempt_started():
    status = read_status()

    status["last_run_status"] = "running"
    status["last_attempted_run"] = now_text()
    status["failure_step"] = ""
    status["failure_message"] = ""

    write_status(status)


def mark_success():
    current_time = now_text()

    status = read_status()

    status["last_run_status"] = "success"
    status["last_successful_run"] = current_time
    status["last_attempted_run"] = current_time
    status["failure_step"] = ""
    status["failure_message"] = ""

    write_status(status)


def mark_failure(failure_step, failure_message):
    status = read_status()

    status["last_run_status"] = "failed"
    status["last_attempted_run"] = now_text()
    status["failure_step"] = str(failure_step)
    status["failure_message"] = str(failure_message)

    write_status(status)


def main():
    command = ""

    if len(sys.argv) >= 2:
        command = sys.argv[1].strip().lower()

    if command in ("", "start", "started", "running"):
        mark_attempt_started()
        print("LINEUP status marked as running.")
        return

    if command == "success":
        mark_success()
        print("LINEUP status marked as successful.")
        return

    if command in ("failed", "failure"):
        failure_step = sys.argv[2] if len(sys.argv) >= 3 else "Unknown step"
        failure_message = sys.argv[3] if len(sys.argv) >= 4 else "Unknown failure"

        mark_failure(failure_step, failure_message)
        print("LINEUP status marked as failed.")
        return

    print(f"Unknown status command: {command}")
    sys.exit(1)


if __name__ == "__main__":
    main()