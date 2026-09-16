from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request

from .history import movement_summary
from .refresh import get_current_payload, refresh_logistics


logistics_bp = Blueprint("logistics", __name__)


def _area_or_404(area_id: str):
    payload = get_current_payload()
    area = payload.get("area_details", {}).get(area_id)
    if area is None:
        abort(404)
    return payload, area


@logistics_bp.route("/logistics")
def overview():
    payload = get_current_payload()
    return render_template(
        "logistics/overview.html",
        payload=payload,
        areas=payload.get("areas", []),
        totals=payload.get("totals", {}),
    )


@logistics_bp.route("/logistics/area/<area_id>")
def area_plan(area_id: str):
    payload, area = _area_or_404(area_id)
    return render_template(
        "logistics/area.html",
        payload=payload,
        area=area,
    )


@logistics_bp.route("/logistics/movements")
def movements():
    payload = get_current_payload()
    return render_template(
        "logistics/movements.html",
        payload=payload,
        areas=payload.get("areas", []),
    )


@logistics_bp.route("/api/logistics/areas")
def api_areas():
    payload = get_current_payload()
    return jsonify({
        "generated_at": payload.get("generated_at"),
        "generated_at_display": payload.get("generated_at_display"),
        "refresh_seconds": payload.get("refresh_seconds", 60),
        "totals": payload.get("totals", {}),
        "areas": payload.get("areas", []),
        "source_state": payload.get("source_state", {}),
    })


@logistics_bp.route("/api/logistics/area/<area_id>")
def api_area(area_id: str):
    payload, area = _area_or_404(area_id)
    return jsonify({
        "generated_at": payload.get("generated_at"),
        "generated_at_display": payload.get("generated_at_display"),
        "refresh_seconds": payload.get("refresh_seconds", 60),
        "source_state": payload.get("source_state", {}),
        "area": area,
    })


@logistics_bp.route("/api/logistics/movements")
def api_movements():
    days = request.args.get("days", 7, type=int)
    limit = request.args.get("limit", 2000, type=int)
    window = str(request.args.get("window", "") or "").strip().lower()
    return jsonify(
        movement_summary(
            days=days,
            limit=limit,
            today_only=(window == "today"),
        )
    )


@logistics_bp.route("/api/logistics/refresh", methods=["POST"])
def api_refresh():
    payload = refresh_logistics(force=True)
    return jsonify({
        "success": True,
        "generated_at": payload.get("generated_at"),
        "history_run_id": payload.get("history_run_id"),
        "history_written": payload.get("history_written"),
    })
