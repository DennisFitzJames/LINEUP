from __future__ import annotations

from datetime import datetime
from flask import Blueprint, abort, jsonify, render_template, request, send_file

from .service import export_area_workbook, get_model, get_plan

production_plans_bp = Blueprint("production_plans", __name__)


@production_plans_bp.route("/production-plans")
def overview():
    model = get_model()
    return render_template("production_plans/overview.html", model=model)


@production_plans_bp.route("/production-plans/work-centre/<work_centre>")
def plan(work_centre: str):
    model = get_model()
    plan_data = get_plan(work_centre)
    if plan_data is None:
        abort(404)
    return render_template("production_plans/plan.html", model=model, plan=plan_data)


@production_plans_bp.route("/production-plans/export")
def export_page():
    model = get_model()
    return render_template("production_plans/export.html", model=model, areas=model["config"].get("export_areas", {}))


@production_plans_bp.route("/production-plans/export/<area_name>")
def download_export(area_name: str):
    model = get_model()
    if area_name not in model["config"].get("export_areas", {}):
        abort(404)
    try:
        stream = export_area_workbook(area_name)
    except ModuleNotFoundError as exc:
        if exc.name == "openpyxl":
            return (
                "Production Plan Excel export requires openpyxl. "
                "From the LINEUP folder run: py -m pip install -r requirements.txt",
                503,
            )
        raise
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(stream, as_attachment=True, download_name=f"{area_name}_Plain_Plans_{stamp}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@production_plans_bp.route("/api/production-plans")
def api_overview():
    model = get_model()
    return jsonify({k: model[k] for k in ("generated_at", "generated_at_display", "refresh_seconds", "totals", "cards", "work_centres")})


@production_plans_bp.route("/api/production-plans/work-centre/<work_centre>")
def api_plan(work_centre: str):
    model = get_model()
    plan_data = get_plan(work_centre)
    if plan_data is None:
        abort(404)
    return jsonify({"generated_at": model["generated_at"], "generated_at_display": model["generated_at_display"], "refresh_seconds": model["refresh_seconds"], "plan": plan_data})
