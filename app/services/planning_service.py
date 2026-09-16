from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from live_work import get_active_benches
from order_repository import load_ready_orders
from planning_board_support import validate_planning_board_payload
from queue_control import (
    add_held_order,
    add_order_to_manual_queue,
    add_order_to_planning_pool,
    clear_manual_queues,
    clear_planning_pool,
    load_queue_control,
    move_order_in_manual_queue,
    release_held_order_to_queue,
    remove_held_order,
    remove_order_from_manual_queue,
    remove_order_from_planning_pool,
    save_queue_control,
)


RecalculateFunction = Callable[[], tuple[bool, str]]
BenchLoader = Callable[[], list[dict[str, Any]]]


@dataclass(frozen=True)
class ActionResult:
    """Outcome returned by a planning service operation."""

    success: bool
    message: str
    status_code: int = 200
    payload: dict[str, Any] | None = None


class PlanningService:
    """
    Application service for Planning Board operations.

    The service deliberately contains no Flask request or response objects.
    Flask routes can therefore call it without owning the business logic.
    """

    def __init__(
        self,
        *,
        load_benches: BenchLoader,
        recalculate: RecalculateFunction,
    ) -> None:
        self._load_benches = load_benches
        self._recalculate = recalculate

    # ------------------------------------------------------------------
    # Ready to Schedule
    # ------------------------------------------------------------------

    def add_ready_order(self, order_number: str, note: str = "") -> ActionResult:
        order_number = self._normalise_required(order_number, "Order number")

        ready_lookup = self._ready_order_lookup()
        if order_number not in ready_lookup:
            return ActionResult(
                False,
                (
                    f"Order {order_number} is not currently ready for production. "
                    "It may still be awaiting picking, completed, delivered, "
                    "or absent from the latest SAP data."
                ),
                400,
            )

        try:
            add_order_to_planning_pool(order_number, note=str(note or "").strip())
        except Exception as error:
            return ActionResult(
                False,
                f"Could not add order {order_number} to Ready to Schedule: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=f"Order {order_number} added to Ready to Schedule.",
            failure_prefix=(
                f"Order {order_number} was added to Ready to Schedule, "
                "but recalculation failed"
            ),
        )

    def remove_ready_order(self, order_number: str) -> ActionResult:
        order_number = self._normalise_required(order_number, "Order number")

        try:
            remove_order_from_planning_pool(order_number)
        except Exception as error:
            return ActionResult(
                False,
                f"Could not remove order {order_number} from Ready to Schedule: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=f"Order {order_number} removed from Ready to Schedule.",
            failure_prefix=(
                f"Order {order_number} was removed from Ready to Schedule, "
                "but recalculation failed"
            ),
        )

    def clear_ready_orders(self) -> ActionResult:
        try:
            removed_count = clear_planning_pool()
        except Exception as error:
            return ActionResult(
                False,
                f"Could not clear Ready to Schedule: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=(
                f"Ready to Schedule cleared. Removed {removed_count} order(s)."
            ),
            failure_prefix=(
                "Ready to Schedule was cleared, but recalculation failed"
            ),
            payload={"removed_count": removed_count},
        )

    # ------------------------------------------------------------------
    # Bench queues
    # ------------------------------------------------------------------

    def add_to_bench_queue(
        self,
        bench_id: str,
        order_number: str,
        note: str = "",
    ) -> ActionResult:
        bench_id = self._normalise_required(bench_id, "Bench")
        order_number = self._normalise_required(order_number, "Order number")

        validation_error = self._validate_ready_order_for_bench(
            order_number=order_number,
            bench_id=bench_id,
        )
        if validation_error:
            return ActionResult(False, validation_error, 400)

        try:
            add_order_to_manual_queue(
                bench_id,
                order_number,
                note=str(note or "").strip(),
            )
        except Exception as error:
            return ActionResult(
                False,
                f"Could not add order {order_number} to {bench_id}: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=f"Order {order_number} added to {bench_id} queue.",
            failure_prefix=(
                f"Order {order_number} was added to {bench_id}, "
                "but recalculation failed"
            ),
        )

    def remove_from_bench_queue(
        self,
        bench_id: str,
        order_number: str,
    ) -> ActionResult:
        bench_id = str(bench_id or "").strip()
        order_number = self._normalise_required(order_number, "Order number")

        try:
            remove_order_from_manual_queue(bench_id, order_number)
        except Exception as error:
            return ActionResult(
                False,
                f"Could not remove order {order_number} from its queue: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=f"Order {order_number} removed from the bench queue.",
            failure_prefix=(
                f"Order {order_number} was removed from the bench queue, "
                "but recalculation failed"
            ),
        )

    def move_in_bench_queue(
        self,
        bench_id: str,
        order_number: str,
        direction: str,
    ) -> ActionResult:
        bench_id = self._normalise_required(bench_id, "Bench")
        order_number = self._normalise_required(order_number, "Order number")
        direction = str(direction or "").strip().lower()

        if direction not in {"up", "down"}:
            return ActionResult(
                False,
                "Queue direction must be 'up' or 'down'.",
                400,
            )

        try:
            move_order_in_manual_queue(bench_id, order_number, direction)
        except Exception as error:
            return ActionResult(
                False,
                f"Could not move order {order_number}: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=f"Order {order_number} moved {direction}.",
            failure_prefix=(
                f"Order {order_number} was moved {direction}, "
                "but recalculation failed"
            ),
        )

    def clear_bench_queues(self) -> ActionResult:
        try:
            removed_count = clear_manual_queues()
        except Exception as error:
            return ActionResult(
                False,
                f"Could not clear the bench queues: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=(
                f"Bench queues cleared. Removed {removed_count} order(s)."
            ),
            failure_prefix=(
                "Bench queues were cleared, but recalculation failed"
            ),
            payload={"removed_count": removed_count},
        )

    # ------------------------------------------------------------------
    # Holds
    # ------------------------------------------------------------------

    def hold_order(
        self,
        order_number: str,
        *,
        bench_id: str = "",
        reason: str = "",
        note: str = "",
    ) -> ActionResult:
        order_number = self._normalise_required(order_number, "Order number")
        bench_id = str(bench_id or "").strip()
        reason = str(reason or "").strip() or "Planner hold"
        note = str(note or "").strip()

        try:
            add_held_order(
                order_number,
                reason=reason,
                note=note,
                bench_id=bench_id,
            )
            remove_order_from_planning_pool(order_number)
            remove_order_from_manual_queue("", order_number)
        except Exception as error:
            return ActionResult(
                False,
                f"Could not hold order {order_number}: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=f"Order {order_number} placed on hold.",
            failure_prefix=(
                f"Order {order_number} was placed on hold, "
                "but recalculation failed"
            ),
        )

    def remove_hold(self, order_number: str) -> ActionResult:
        order_number = self._normalise_required(order_number, "Order number")

        try:
            remove_held_order(order_number)
        except Exception as error:
            return ActionResult(
                False,
                f"Could not remove the hold from order {order_number}: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=f"Hold removed from order {order_number}.",
            failure_prefix=(
                f"The hold was removed from order {order_number}, "
                "but recalculation failed"
            ),
        )

    def release_hold_to_queue(
        self,
        order_number: str,
        bench_id: str,
    ) -> ActionResult:
        order_number = self._normalise_required(order_number, "Order number")
        bench_id = self._normalise_required(bench_id, "Bench")

        validation_error = self._validate_ready_order_for_bench(
            order_number=order_number,
            bench_id=bench_id,
        )
        if validation_error:
            return ActionResult(False, validation_error, 400)

        try:
            release_held_order_to_queue(order_number, bench_id)
        except Exception as error:
            return ActionResult(
                False,
                f"Could not release order {order_number} to {bench_id}: {error}",
                400,
            )

        return self._recalculate_result(
            success_message=(
                f"Order {order_number} released from hold to {bench_id}."
            ),
            failure_prefix=(
                f"Order {order_number} was released to {bench_id}, "
                "but recalculation failed"
            ),
        )

    # ------------------------------------------------------------------
    # Whole-board save
    # ------------------------------------------------------------------

    def save_board(self, payload: Mapping[str, Any] | None) -> ActionResult:
        try:
            state = self._save_board_state(payload)
        except Exception as error:
            return ActionResult(False, str(error), 400)

        result = self._recalculate_result(
            success_message="Planning Board saved and LINEUP recalculated.",
            failure_prefix=(
                "Planning Board was saved, but recalculation failed"
            ),
            payload={"state": state},
        )

        if result.success:
            return result

        return ActionResult(
            False,
            result.message,
            500,
            result.payload,
        )

    def _save_board_state(
        self,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        ready_orders = load_ready_orders()
        order_lookup = {
            str(order.get("order_number", "")).strip(): order
            for order in ready_orders
            if str(order.get("order_number", "")).strip()
        }

        benches = self._load_benches()
        bench_lookup = {
            str(bench.get("bench_id", "")).strip(): bench
            for bench in benches
            if str(bench.get("bench_id", "")).strip()
        }

        clean_payload = validate_planning_board_payload(
            payload=payload,
            order_lookup=order_lookup,
            bench_lookup=bench_lookup,
            live_benches=get_active_benches(),
        )

        previous_state = load_queue_control()
        previous_notes = self._collect_previous_notes(previous_state)
        now_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        clean_pool = [
            self._board_item(
                item["order_number"],
                previous_notes=previous_notes,
                now_value=now_value,
            )
            for item in clean_payload["planning_pool"]
        ]

        clean_queues: dict[str, list[dict[str, str]]] = {}
        for bench_id, items in clean_payload["manual_queues"].items():
            clean_items = [
                self._board_item(
                    item["order_number"],
                    previous_notes=previous_notes,
                    now_value=now_value,
                )
                for item in items
            ]
            if clean_items:
                clean_queues[bench_id] = clean_items

        state = load_queue_control()
        state["version"] = max(2, self._safe_int(state.get("version"), 2))
        state["planning_pool"] = clean_pool
        state["manual_queues"] = clean_queues

        board_orders = {
            item["order_number"]
            for item in clean_pool
        }
        for items in clean_queues.values():
            board_orders.update(item["order_number"] for item in items)

        held_orders = state.setdefault("held_orders", {})
        if not isinstance(held_orders, dict):
            held_orders = {}
            state["held_orders"] = held_orders

        for order_number in board_orders:
            held_orders.pop(order_number, None)

        save_queue_control(state)
        return state

    # ------------------------------------------------------------------
    # Validation and support
    # ------------------------------------------------------------------

    def _validate_ready_order_for_bench(
        self,
        *,
        order_number: str,
        bench_id: str,
    ) -> str:
        ready_lookup = self._ready_order_lookup()
        order = ready_lookup.get(order_number)
        if order is None:
            return (
                f"Order {order_number} is not currently ready for production. "
                "Only Ready to Schedule orders can be assigned to a bench."
            )

        bench_lookup = {
            str(bench.get("bench_id", "")).strip(): bench
            for bench in self._load_benches()
            if str(bench.get("bench_id", "")).strip()
        }
        bench = bench_lookup.get(bench_id)
        if bench is None:
            return f"Bench {bench_id} was not found."

        if str(bench.get("is_open", "yes")).strip().lower() != "yes":
            return f"Bench {bench_id} is closed."

        order_pool = str(order.get("scheduling_pool", "")).strip()
        bench_pool = str(bench.get("scheduling_pool", "")).strip()
        if order_pool and bench_pool and order_pool != bench_pool:
            return (
                f"Order {order_number} is not compatible with bench {bench_id}."
            )

        return ""

    def _ready_order_lookup(self) -> dict[str, dict[str, Any]]:
        return {
            str(order.get("order_number", "")).strip(): order
            for order in load_ready_orders()
            if str(order.get("order_number", "")).strip()
        }

    def _recalculate_result(
        self,
        *,
        success_message: str,
        failure_prefix: str,
        payload: dict[str, Any] | None = None,
    ) -> ActionResult:
        try:
            ok, run_message = self._recalculate()
        except Exception as error:
            return ActionResult(
                False,
                f"{failure_prefix}: {error}",
                500,
                payload,
            )

        if ok:
            return ActionResult(True, success_message, 200, payload)

        return ActionResult(
            False,
            f"{failure_prefix}: {run_message}",
            500,
            payload,
        )

    @staticmethod
    def _normalise_required(value: Any, label: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{label} is required.")
        return text

    @staticmethod
    def _collect_previous_notes(
        state: Mapping[str, Any],
    ) -> dict[str, str]:
        previous_notes: dict[str, str] = {}

        for item in state.get("planning_pool", []) or []:
            if not isinstance(item, Mapping):
                continue
            order_number = str(item.get("order_number", "")).strip()
            if order_number:
                previous_notes[order_number] = str(
                    item.get("note", "")
                ).strip()

        manual_queues = state.get("manual_queues", {}) or {}
        if isinstance(manual_queues, Mapping):
            for items in manual_queues.values():
                for item in items or []:
                    if not isinstance(item, Mapping):
                        continue
                    order_number = str(
                        item.get("order_number", "")
                    ).strip()
                    if order_number:
                        previous_notes[order_number] = str(
                            item.get("note", "")
                        ).strip()

        return previous_notes

    @staticmethod
    def _board_item(
        order_number: str,
        *,
        previous_notes: Mapping[str, str],
        now_value: str,
    ) -> dict[str, str]:
        return {
            "order_number": order_number,
            "added_at": now_value,
            "added_by": "planning_board",
            "note": previous_notes.get(order_number, ""),
        }

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
