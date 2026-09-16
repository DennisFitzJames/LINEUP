from __future__ import annotations

from datetime import date, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def clean_text(value: Any) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def normalise_order_number(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def to_float(value: Any, default: float = 0.0) -> float:
    text = clean_text(value).replace(",", "")
    if text == "":
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(to_float(value, float(default))))
    except (TypeError, ValueError):
        return default


def parse_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None

    for pattern in DATE_FORMATS:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    parsed = parse_datetime(value)
    return parsed.date() if parsed else None


def iso_date(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


def display_date(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else ""


def status_tokens(value: Any) -> list[str]:
    text = clean_text(value).upper()
    return re.findall(r"[A-Z0-9*]+", text)


def determine_order_status(
    system_status: Any,
    user_status: Any,
    staged_from_lx02: bool = False,
) -> str:
    system_tokens = status_tokens(system_status)
    user_text = clean_text(user_status).upper()

    if "TECO" in system_tokens:
        return "TECO"
    if "PCNF" in system_tokens:
        return "PCNF"
    if "CNF" in system_tokens:
        return "CNF"
    if "DLV" in system_tokens:
        return "COMPLETED"

    if staged_from_lx02 or "COMP" in user_text or "PREP" in user_text:
        return "STAGED"

    if "REL" in system_tokens:
        return "REL"

    return "CRTD"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def is_next_week(day: date | None, today: date | None = None) -> bool:
    if day is None:
        return False
    today = today or date.today()
    next_monday = week_start(today) + timedelta(days=7)
    return next_monday <= day <= next_monday + timedelta(days=6)


def signed_day_delta(old_value: Any, new_value: Any) -> int | None:
    old_date = parse_date(old_value)
    new_date = parse_date(new_value)
    if not old_date or not new_date:
        return None
    return (new_date - old_date).days


def source_signature(paths: Iterable[Path]) -> str:
    payload = []
    for path in paths:
        path = Path(path)
        if path.exists():
            stat = path.stat()
            payload.append({
                "path": str(path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            })
        else:
            payload.append({"path": str(path.resolve()), "missing": True})

    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_clock(value: str, fallback: time) -> time:
    text = clean_text(value)
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, pattern).time()
        except ValueError:
            continue
    return fallback


def forecast_remaining(
    picker_count: int,
    orders_per_person: int,
    now: datetime,
    start_text: str = "07:50",
    workday_hours: float = 9.0,
) -> float:
    full_target = max(0, picker_count) * max(0, orders_per_person)
    if full_target <= 0:
        return 0.0

    start_time = parse_clock(start_text, time(7, 50))
    start_at = datetime.combine(now.date(), start_time)

    if now <= start_at:
        return float(full_target)

    elapsed_hours = max(0.0, (now - start_at).total_seconds() / 3600)
    remaining = full_target - (full_target / max(workday_hours, 0.1)) * elapsed_hours
    return max(0.0, remaining)
