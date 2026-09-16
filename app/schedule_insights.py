from datetime import date

from working_calendar import (
    planned_day_offset,
    work_minute_to_shift_time,
)


CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_ATTENTION = "ATTENTION"

SOURCE_LIVE = "LIVE"
SOURCE_PLANNER = "PLANNER"
SOURCE_SPLIT = "SPLIT"
SOURCE_FORCED = "FORCED"
SOURCE_STABLE = "STABLE"
SOURCE_OPTIMISED = "OPTIMISED"

STABILITY_LIVE = "LIVE LOCK"
STABILITY_PLANNER = "PLANNER LOCK"
STABILITY_SPLIT = "SPLIT LOCK"
STABILITY_FORCED = "FORCED LOCK"
STABILITY_STABLE = "STABLE NEXT"
STABILITY_FLEXIBLE = "FLEXIBLE"


def parse_int(value, default=0):
    try:
        text = str(value or "").strip()

        if not text:
            return default

        return int(float(text))

    except (TypeError, ValueError):
        return default


def parse_float(value, default=0.0):
    try:
        text = str(value or "").strip()

        if not text:
            return default

        return float(text)

    except (TypeError, ValueError):
        return default


def normalise_text(value):
    return str(value or "").strip()


def source_details(
    assignment_source,
    bench_id="",
    previous_bench_id="",
):
    assignment_source = normalise_text(
        assignment_source
    ).upper()

    bench_id = normalise_text(bench_id)
    previous_bench_id = normalise_text(
        previous_bench_id
    )

    if assignment_source == SOURCE_LIVE:
        return {
            "source_label": "Live WIP",
            "queue_stability": STABILITY_LIVE,
            "assignment_reason": (
                "The order is actively being tracked on this bench, "
                "so it remains the current order."
            ),
        }

    if assignment_source == SOURCE_PLANNER:
        return {
            "source_label": "Planner",
            "queue_stability": STABILITY_PLANNER,
            "assignment_reason": (
                "The planner placed this order in this bench queue "
                "using the Planning Board."
            ),
        }

    if assignment_source == SOURCE_SPLIT:
        return {
            "source_label": "Split",
            "queue_stability": STABILITY_SPLIT,
            "assignment_reason": (
                "This is a manually created split part assigned "
                "to this bench."
            ),
        }

    if assignment_source == SOURCE_FORCED:
        return {
            "source_label": "Forced",
            "queue_stability": STABILITY_FORCED,
            "assignment_reason": (
                "An advanced override assigned this order "
                f"to {bench_id or 'this bench'}."
            ),
        }

    if assignment_source == SOURCE_STABLE:
        previous_text = ""

        if previous_bench_id:
            previous_text = (
                f" It was previously assigned to {previous_bench_id}."
            )

        return {
            "source_label": "Stable Queue",
            "queue_stability": STABILITY_STABLE,
            "assignment_reason": (
                "LINEUP preserved this near-term automatic assignment "
                "to stop the next order changing unnecessarily."
                f"{previous_text}"
            ),
        }

    return {
        "source_label": "Optimised",
        "queue_stability": STABILITY_FLEXIBLE,
        "assignment_reason": (
            "LINEUP selected this compatible bench using due risk, "
            "predicted finish time, priority and material continuity."
        ),
    }


def candidate_summary(
    order,
    selected_bench,
    eligible_benches,
    base_date=None,
):
    if base_date is None:
        base_date = date.today()

    selected_bench_id = normalise_text(
        selected_bench.get("bench_id", "")
    )

    selected_finish_minute = parse_int(
        selected_bench.get(
            "candidate_finish_minute",
            0
        ),
        0
    )

    selected_finish_offset = planned_day_offset(
        base_date,
        selected_finish_minute,
        is_finish=True,
    )

    selected_finish_text = work_minute_to_shift_time(
        base_date,
        selected_finish_minute,
        is_finish=True,
    )

    target_offset = parse_int(
        order.get("target_finish_day_offset", ""),
        None,
    )

    selected_late_days = 0

    if target_offset is not None:
        selected_late_days = max(
            0,
            selected_finish_offset - target_offset,
        )

    ranked = []

    for bench in eligible_benches:
        finish_minute = parse_int(
            bench.get(
                "candidate_finish_minute",
                0
            ),
            0
        )

        finish_offset = planned_day_offset(
            base_date,
            finish_minute,
            is_finish=True,
        )

        late_days = 0

        if target_offset is not None:
            late_days = max(
                0,
                finish_offset - target_offset,
            )

        ranked.append({
            "bench_id": normalise_text(
                bench.get("bench_id", "")
            ),
            "finish_minute": finish_minute,
            "finish_offset": finish_offset,
            "late_days": late_days,
            "penalty": parse_float(
                bench.get(
                    "candidate_penalty",
                    0
                ),
                0.0,
            ),
            "same_last_material": bool(
                bench.get(
                    "candidate_same_last_material",
                    False
                )
            ),
            "has_same_material": bool(
                bench.get(
                    "candidate_has_same_material",
                    False
                )
            ),
        })

    ranked.sort(
        key=lambda candidate: (
            candidate["penalty"],
            candidate["finish_minute"],
            candidate["bench_id"],
        )
    )

    alternatives = [
        candidate
        for candidate in ranked
        if candidate["bench_id"] != selected_bench_id
    ]

    reason_parts = []

    if selected_late_days == 0:
        reason_parts.append(
            "This bench gives an on-time predicted finish."
        )
    elif selected_late_days == 1:
        reason_parts.append(
            "No evaluated option fully recovered the order; "
            "this bench produced the strongest overall result."
        )
    else:
        reason_parts.append(
            "The order remains late, but this bench produced "
            "the strongest overall result among compatible benches."
        )

    if selected_bench.get(
        "candidate_same_last_material",
        False
    ):
        reason_parts.append(
            "The immediately preceding work uses the same material."
        )

    elif selected_bench.get(
        "candidate_has_same_material",
        False
    ):
        reason_parts.append(
            "This bench already has the same material in its queue."
        )

    if alternatives:
        next_best = alternatives[0]

        if (
            next_best["late_days"]
            > selected_late_days
        ):
            reason_parts.append(
                f"The next-best bench, {next_best['bench_id']}, "
                "would create more due-date risk."
            )

        elif (
            next_best["finish_minute"]
            > selected_finish_minute
        ):
            reason_parts.append(
                f"The next-best bench, {next_best['bench_id']}, "
                "would finish later."
            )

    return {
        "assignment_reason": " ".join(reason_parts),
        "predicted_finish_text": selected_finish_text,
        "predicted_finish_day_offset": selected_finish_offset,
        "predicted_late_days": selected_late_days,
        "evaluated_bench_count": len(ranked),
        "selected_bench_rank": 1,
    }


def confidence_details(
    assignment_source,
    due_status,
    staffing_factor=1.0,
    staffing_override_people="",
    is_live=False,
    split_part=False,
):
    assignment_source = normalise_text(
        assignment_source
    ).upper()

    due_status = normalise_text(
        due_status
    ).upper()

    staffing_factor = parse_float(
        staffing_factor,
        1.0,
    )

    staffing_override_people = normalise_text(
        staffing_override_people
    )

    attention_reasons = []

    if due_status == "LATE":
        attention_reasons.append(
            "The predicted finish is later than the SAP scheduled finish day."
        )

    if (
        staffing_override_people
        and abs(staffing_factor - 1.0) >= 0.20
    ):
        attention_reasons.append(
            "A manual staffing override materially changes the duration."
        )

    if split_part and due_status == "LATE":
        attention_reasons.append(
            "The split part is still predicted to finish late."
        )

    if attention_reasons:
        return {
            "schedule_confidence": CONFIDENCE_ATTENTION,
            "confidence_reason": " ".join(
                attention_reasons
            ),
        }

    if is_live or assignment_source == SOURCE_LIVE:
        return {
            "schedule_confidence": CONFIDENCE_HIGH,
            "confidence_reason": (
                "This is live tracked work and is locked "
                "to the current bench."
            ),
        }

    if assignment_source in (
        SOURCE_PLANNER,
        SOURCE_SPLIT,
        SOURCE_FORCED,
    ):
        return {
            "schedule_confidence": CONFIDENCE_HIGH,
            "confidence_reason": (
                "The assignment is explicitly controlled "
                "by the planner."
            ),
        }

    if assignment_source == SOURCE_STABLE:
        return {
            "schedule_confidence": CONFIDENCE_MEDIUM,
            "confidence_reason": (
                "The order is stable on this bench, but its timing "
                "still depends on preceding work completing as forecast."
            ),
        }

    if due_status in (
        "ON TARGET",
        "AHEAD",
    ):
        return {
            "schedule_confidence": CONFIDENCE_MEDIUM,
            "confidence_reason": (
                "The current automatic plan is on target, but later "
                "automatic queue positions may still be re-optimised."
            ),
        }

    return {
        "schedule_confidence": CONFIDENCE_MEDIUM,
        "confidence_reason": (
            "The assignment is currently valid, but LINEUP has limited "
            "due-date information for this order."
        ),
    }


def build_schedule_insight(
    order,
    bench,
    assignment_source,
    due_status,
    base_assignment_reason="",
    previous_bench_id="",
    is_live=False,
    split_part=False,
    optimisation_details=None,
):
    assignment_source = normalise_text(
        assignment_source
    ).upper()

    source = source_details(
        assignment_source=assignment_source,
        bench_id=bench.get("bench_id", ""),
        previous_bench_id=previous_bench_id,
    )

    assignment_reason = normalise_text(
        base_assignment_reason
    )

    if not assignment_reason:
        assignment_reason = source[
            "assignment_reason"
        ]

    if optimisation_details:
        optimisation_reason = normalise_text(
            optimisation_details.get(
                "assignment_reason",
                ""
            )
        )

        if optimisation_reason:
            assignment_reason = optimisation_reason

    confidence = confidence_details(
        assignment_source=assignment_source,
        due_status=due_status,
        staffing_factor=bench.get(
            "staffing_factor",
            1.0,
        ),
        staffing_override_people=bench.get(
            "staffing_override_people",
            "",
        ),
        is_live=is_live,
        split_part=split_part,
    )

    return {
        "assignment_source": assignment_source,
        "assignment_source_label": source[
            "source_label"
        ],
        "assignment_reason": assignment_reason,
        "queue_stability": source[
            "queue_stability"
        ],
        "schedule_confidence": confidence[
            "schedule_confidence"
        ],
        "confidence_reason": confidence[
            "confidence_reason"
        ],
    }


def readable_assignment_label(
    assignment_source
):
    assignment_source = normalise_text(
        assignment_source
    ).upper()

    labels = {
        SOURCE_LIVE: "Live WIP",
        SOURCE_PLANNER: "Planner",
        SOURCE_SPLIT: "Split",
        SOURCE_FORCED: "Forced",
        SOURCE_STABLE: "Stable Queue",
        SOURCE_OPTIMISED: "Optimised",
    }

    return labels.get(
        assignment_source,
        assignment_source.title()
        if assignment_source
        else "Optimised",
    )


def readable_confidence_label(
    confidence
):
    confidence = normalise_text(
        confidence
    ).upper()

    labels = {
        CONFIDENCE_HIGH: "High confidence",
        CONFIDENCE_MEDIUM: "Medium confidence",
        CONFIDENCE_ATTENTION: "Planner attention",
    }

    return labels.get(
        confidence,
        "Medium confidence",
    )


if __name__ == "__main__":
    print()
    print("===================================")
    print("LINEUP Schedule Insights")
    print("===================================")
    print("Assignment sources:")
    print("  LIVE")
    print("  PLANNER")
    print("  SPLIT")
    print("  FORCED")
    print("  STABLE")
    print("  OPTIMISED")
    print()
    print("Confidence levels:")
    print("  HIGH")
    print("  MEDIUM")
    print("  ATTENTION")
    print()