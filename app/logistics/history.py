from __future__ import annotations

from datetime import date, datetime, timedelta
import sqlite3
from typing import Any

from .config import PROJECT_ROOT
from .utils import parse_date, signed_day_delta


DATABASE_FILE = PROJECT_ROOT / "data" / "logistics" / "logistics_history.sqlite3"
PLANNING_CHANGE_TYPES = ("date_moved", "teco")


SCHEMA = """
CREATE TABLE IF NOT EXISTS refresh_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    source_signature TEXT NOT NULL,
    active_count INTEGER NOT NULL DEFAULT 0,
    picked_count INTEGER NOT NULL DEFAULT 0,
    teco_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_signature)
);

CREATE TABLE IF NOT EXISTS order_snapshots (
    run_id INTEGER NOT NULL,
    order_number TEXT NOT NULL,
    area_id TEXT NOT NULL,
    area_name TEXT NOT NULL,
    work_centres TEXT,
    scheduled_start TEXT,
    scheduled_finish TEXT,
    status TEXT,
    system_status TEXT,
    user_status TEXT,
    hours_required REAL NOT NULL DEFAULT 0,
    remaining_hours REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, order_number, area_id),
    FOREIGN KEY (run_id) REFERENCES refresh_runs(run_id)
);

CREATE TABLE IF NOT EXISTS order_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    detected_at TEXT NOT NULL,
    order_number TEXT NOT NULL,
    area_id TEXT NOT NULL,
    area_name TEXT NOT NULL,
    change_type TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    days_delta INTEGER,
    FOREIGN KEY (run_id) REFERENCES refresh_runs(run_id)
);

CREATE INDEX IF NOT EXISTS ix_changes_detected_at
ON order_changes(detected_at);

CREATE INDEX IF NOT EXISTS ix_changes_area
ON order_changes(area_id, detected_at);

CREATE INDEX IF NOT EXISTS ix_snapshots_order
ON order_snapshots(order_number, area_id, run_id);
"""


def _connect() -> sqlite3.Connection:
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def _latest_run(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM refresh_runs ORDER BY run_id DESC LIMIT 1"
    ).fetchone()


def _snapshot_map(
    connection: sqlite3.Connection,
    run_id: int | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not run_id:
        return {}

    rows = connection.execute(
        """
        SELECT *
        FROM order_snapshots
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()

    return {
        (row["order_number"], row["area_id"]): dict(row)
        for row in rows
    }


def _insert_change(
    connection: sqlite3.Connection,
    *,
    run_id: int,
    detected_at: str,
    row: dict[str, Any],
    change_type: str,
    old_value: Any = "",
    new_value: Any = "",
    days_delta: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO order_changes (
            run_id,
            detected_at,
            order_number,
            area_id,
            area_name,
            change_type,
            old_value,
            new_value,
            days_delta
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            detected_at,
            row.get("order_number", ""),
            row.get("area_id", ""),
            row.get("area_name", ""),
            change_type,
            str(old_value or ""),
            str(new_value or ""),
            days_delta,
        ),
    )


def record_snapshot(
    payload: dict[str, Any],
    source_signature: str,
) -> tuple[int, bool]:
    captured_at = str(
        payload.get("generated_at")
        or datetime.now().isoformat(timespec="seconds")
    )
    snapshot_rows = list(payload.get("snapshot_rows", []))
    totals = payload.get("totals", {})

    with _connect() as connection:
        existing = connection.execute(
            "SELECT run_id FROM refresh_runs WHERE source_signature = ?",
            (source_signature,),
        ).fetchone()
        if existing:
            return int(existing["run_id"]), False

        previous = _latest_run(connection)
        previous_run_id = int(previous["run_id"]) if previous else None
        previous_map = _snapshot_map(connection, previous_run_id)

        cursor = connection.execute(
            """
            INSERT INTO refresh_runs (
                captured_at,
                source_signature,
                active_count,
                picked_count,
                teco_count
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                captured_at,
                source_signature,
                int(totals.get("active_count", 0) or 0),
                int(totals.get("picked_count", 0) or 0),
                int(totals.get("teco_count", 0) or 0),
            ),
        )
        run_id = int(cursor.lastrowid)

        current_map: dict[tuple[str, str], dict[str, Any]] = {}

        for row in snapshot_rows:
            order_number = str(row.get("order_number", "")).strip()
            area_id = str(row.get("area_id", "")).strip()
            if not order_number or not area_id:
                continue

            current_map[(order_number, area_id)] = row
            connection.execute(
                """
                INSERT INTO order_snapshots (
                    run_id,
                    order_number,
                    area_id,
                    area_name,
                    work_centres,
                    scheduled_start,
                    scheduled_finish,
                    status,
                    system_status,
                    user_status,
                    hours_required,
                    remaining_hours
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    order_number,
                    area_id,
                    row.get("area_name", ""),
                    row.get("work_centres", ""),
                    row.get("scheduled_start", ""),
                    row.get("scheduled_finish", ""),
                    row.get("status", ""),
                    row.get("system_status", ""),
                    row.get("user_status", ""),
                    float(row.get("hours_required", 0) or 0),
                    float(row.get("remaining_hours", 0) or 0),
                ),
            )

        # Movement history is deliberately limited to planning-significant
        # events: scheduled-date changes and newly TECO orders. Lifecycle
        # transitions such as REL -> STAGED are still stored in snapshots but
        # no longer create movement events.
        if previous_run_id is not None:
            for key, current in current_map.items():
                previous_row = previous_map.get(key)
                if previous_row is None:
                    continue

                old_start = previous_row.get("scheduled_start", "")
                new_start = current.get("scheduled_start", "")
                if old_start != new_start:
                    delta = signed_day_delta(old_start, new_start)
                    _insert_change(
                        connection,
                        run_id=run_id,
                        detected_at=captured_at,
                        row=current,
                        change_type="date_moved",
                        old_value=old_start,
                        new_value=new_start,
                        days_delta=delta,
                    )

                old_status = str(previous_row.get("status", "") or "")
                new_status = str(current.get("status", "") or "")
                if old_status != "TECO" and new_status == "TECO":
                    _insert_change(
                        connection,
                        run_id=run_id,
                        detected_at=captured_at,
                        row=current,
                        change_type="teco",
                        old_value=old_status,
                        new_value=new_status,
                    )

        connection.commit()
        return run_id, True


def latest_run_details() -> dict[str, Any]:
    with _connect() as connection:
        row = _latest_run(connection)
        return dict(row) if row else {}


def _week_bounds(reference: datetime) -> tuple[date, date]:
    start = reference.date() - timedelta(days=reference.weekday())
    return start, start + timedelta(days=6)


def _week_transition(
    old_value: Any,
    new_value: Any,
    week_start: date,
    week_end: date,
) -> str:
    old_date = parse_date(old_value)
    new_date = parse_date(new_value)
    if old_date is None or new_date is None:
        return ""

    old_in_week = week_start <= old_date <= week_end
    new_in_week = week_start <= new_date <= week_end

    if old_date > week_end and new_in_week:
        return "pulled_in"
    if old_in_week and new_date > week_end:
        return "pushed_out"
    return ""


def movement_summary(
    days: int = 7,
    limit: int = 2000,
    today_only: bool = False,
) -> dict[str, Any]:
    days = max(1, min(int(days or 7), 90))
    limit = max(1, min(int(limit or 2000), 5000))

    now = datetime.now()
    if today_only:
        since_datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        since_datetime = now - timedelta(days=days)

    since = since_datetime.isoformat(timespec="seconds")
    week_start, week_end = _week_bounds(now)

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM order_changes
            WHERE detected_at >= ?
              AND change_type IN ('date_moved', 'teco')
            ORDER BY detected_at DESC, change_id DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()

        all_rows: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["week_transition"] = (
                _week_transition(
                    item.get("old_value", ""),
                    item.get("new_value", ""),
                    week_start,
                    week_end,
                )
                if item.get("change_type") == "date_moved"
                else ""
            )
            all_rows.append(item)

        summary_row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_changes,
                SUM(CASE WHEN change_type = 'date_moved' THEN 1 ELSE 0 END) AS date_moves,
                COUNT(DISTINCT CASE
                    WHEN change_type = 'date_moved' THEN order_number
                    ELSE NULL
                END) AS orders_moved,
                SUM(CASE WHEN change_type = 'date_moved' AND days_delta < 0 THEN 1 ELSE 0 END) AS moved_earlier,
                SUM(CASE WHEN change_type = 'date_moved' AND days_delta > 0 THEN 1 ELSE 0 END) AS moved_later,
                SUM(CASE
                    WHEN change_type = 'date_moved' THEN ABS(COALESCE(days_delta, 0))
                    ELSE 0
                END) AS gross_days,
                SUM(CASE WHEN change_type = 'teco' THEN 1 ELSE 0 END) AS teco,
                COUNT(DISTINCT CASE
                    WHEN change_type = 'teco' THEN order_number
                    ELSE NULL
                END) AS teco_orders
            FROM order_changes
            WHERE detected_at >= ?
              AND change_type IN ('date_moved', 'teco')
            """,
            (since,),
        ).fetchone()

        area_rows = connection.execute(
            """
            SELECT
                area_id,
                area_name,
                COUNT(*) AS change_count,
                SUM(CASE
                    WHEN change_type = 'date_moved' THEN ABS(COALESCE(days_delta, 0))
                    ELSE 0
                END) AS gross_days,
                SUM(CASE WHEN change_type = 'date_moved' AND days_delta < 0 THEN 1 ELSE 0 END) AS moved_earlier,
                SUM(CASE WHEN change_type = 'date_moved' AND days_delta > 0 THEN 1 ELSE 0 END) AS moved_later,
                SUM(CASE WHEN change_type = 'teco' THEN 1 ELSE 0 END) AS teco_count
            FROM order_changes
            WHERE detected_at >= ?
              AND change_type IN ('date_moved', 'teco')
            GROUP BY area_id, area_name
            ORDER BY gross_days DESC, change_count DESC, area_name
            """,
            (since,),
        ).fetchall()

        daily_rows = connection.execute(
            """
            SELECT
                substr(detected_at, 1, 10) AS change_date,
                COUNT(*) AS change_count,
                SUM(CASE WHEN change_type = 'date_moved' THEN 1 ELSE 0 END) AS date_moves,
                SUM(CASE WHEN change_type = 'teco' THEN 1 ELSE 0 END) AS teco_count
            FROM order_changes
            WHERE detected_at >= ?
              AND change_type IN ('date_moved', 'teco')
            GROUP BY substr(detected_at, 1, 10)
            ORDER BY change_date
            """,
            (since,),
        ).fetchall()

        daily_area_rows = connection.execute(
            """
            SELECT
                substr(detected_at, 1, 10) AS change_date,
                change_type,
                area_id,
                area_name,
                COUNT(*) AS event_count,
                COUNT(DISTINCT order_number) AS order_count,
                SUM(CASE
                    WHEN change_type = 'date_moved' THEN ABS(COALESCE(days_delta, 0))
                    ELSE 0
                END) AS gross_days
            FROM order_changes
            WHERE detected_at >= ?
              AND change_type IN ('date_moved', 'teco')
            GROUP BY
                substr(detected_at, 1, 10),
                change_type,
                area_id,
                area_name
            ORDER BY change_date, change_type, event_count DESC, area_name
            """,
            (since,),
        ).fetchall()

        direction_area_rows = connection.execute(
            """
            SELECT
                CASE
                    WHEN change_type = 'date_moved' AND days_delta < 0 THEN 'earlier'
                    WHEN change_type = 'date_moved' AND days_delta > 0 THEN 'later'
                    WHEN change_type = 'teco' THEN 'teco'
                    ELSE ''
                END AS direction,
                area_id,
                area_name,
                COUNT(*) AS event_count,
                COUNT(DISTINCT order_number) AS order_count,
                SUM(CASE
                    WHEN change_type = 'date_moved' THEN ABS(COALESCE(days_delta, 0))
                    ELSE 0
                END) AS gross_days
            FROM order_changes
            WHERE detected_at >= ?
              AND (
                    (change_type = 'date_moved' AND COALESCE(days_delta, 0) <> 0)
                    OR change_type = 'teco'
                  )
            GROUP BY direction, area_id, area_name
            ORDER BY direction, event_count DESC, area_name
            """,
            (since,),
        ).fetchall()

        boundary_rows = connection.execute(
            """
            SELECT order_number, area_id, area_name, old_value, new_value
            FROM order_changes
            WHERE detected_at >= ?
              AND change_type = 'date_moved'
            """,
            (since,),
        ).fetchall()

    summary = dict(summary_row) if summary_row else {}
    summary = {
        key: int(value or 0)
        for key, value in summary.items()
    }

    daily_areas: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in daily_area_rows:
        item = dict(row)
        change_date = str(item.pop("change_date", "") or "")
        change_type = str(item.pop("change_type", "") or "")
        if not change_date or change_type not in PLANNING_CHANGE_TYPES:
            continue
        daily_areas.setdefault(
            change_date,
            {"date_moved": [], "teco": []},
        )[change_type].append(item)

    direction_areas: dict[str, list[dict[str, Any]]] = {
        "earlier": [],
        "later": [],
        "teco": [],
    }
    for row in direction_area_rows:
        item = dict(row)
        direction = str(item.pop("direction", "") or "")
        if direction in direction_areas:
            direction_areas[direction].append(item)

    pulled_in_orders: set[str] = set()
    pushed_out_orders: set[str] = set()
    pulled_in_events = 0
    pushed_out_events = 0

    for row in boundary_rows:
        transition = _week_transition(
            row["old_value"],
            row["new_value"],
            week_start,
            week_end,
        )
        if transition == "pulled_in":
            pulled_in_events += 1
            pulled_in_orders.add(str(row["order_number"] or ""))
        elif transition == "pushed_out":
            pushed_out_events += 1
            pushed_out_orders.add(str(row["order_number"] or ""))

    week_boundary = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "week_start_display": week_start.strftime("%d/%m/%Y"),
        "week_end_display": week_end.strftime("%d/%m/%Y"),
        "pulled_in_orders": len(pulled_in_orders),
        "pulled_in_events": pulled_in_events,
        "pushed_out_orders": len(pushed_out_orders),
        "pushed_out_events": pushed_out_events,
    }

    return {
        "window_days": 1 if today_only else days,
        "window_mode": "today" if today_only else "rolling",
        "window_start": since,
        "generated_at": now.isoformat(timespec="seconds"),
        "summary": summary,
        "week_boundary": week_boundary,
        "areas": [dict(row) for row in area_rows],
        "daily": [dict(row) for row in daily_rows],
        "daily_areas": daily_areas,
        "direction_areas": direction_areas,
        "changes": all_rows,
        "returned_change_count": len(all_rows),
        "latest_run": latest_run_details(),
    }
