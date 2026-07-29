from typing import Dict

# ---------------------------------------------------------------------
# SAP status definitions
# ---------------------------------------------------------------------

READY_USER_STATUSES = {
    "PREP",
    "COMP PREP",
    "COMP",
}

DELIVERED_SYSTEM_STATUSES = {
    "DLV",
}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _tokens(value: str) -> list[str]:
    """
    Split SAP status strings into comparable tokens.
    """

    text = str(value or "").upper()

    text = (
        text.replace(",", " ")
            .replace(";", " ")
            .replace("/", " ")
    )

    return [part.strip() for part in text.split() if part.strip()]


def _contains_phrase(status: str, phrase: str) -> bool:
    """
    Returns True if the complete phrase exists in the status string.

    Example:

        REL COMP PREP

    contains

        COMP PREP
    """

    status = " ".join(_tokens(status))
    phrase = " ".join(_tokens(phrase))

    return phrase in status


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def is_ready_status(order: Dict) -> bool:
    """
    Returns True if the SAP User Status indicates the order is
    physically ready to enter production.
    """

    user_status = str(order.get("user_status", ""))

    return any(
        _contains_phrase(user_status, status)
        for status in READY_USER_STATUSES
    )


def is_picked(order: Dict) -> bool:
    """
    Compatibility wrapper.

    Historically LINEUP used the term "picked".
    Internally this now means "ready for production".
    """

    return is_ready_status(order)


def is_delivered(order: Dict) -> bool:

    combined = (
        _tokens(order.get("system_status", ""))
        + _tokens(order.get("user_status", ""))
    )

    return any(
        token in DELIVERED_SYSTEM_STATUSES
        for token in combined
    )


def remaining_minutes(order: Dict) -> int:

    try:
        return max(
            0,
            int(float(order.get("bench_remaining_minutes", 0))),
        )
    except Exception:
        return 0


def is_ready_for_production(order: Dict) -> bool:
    """
    Central business rule.

    An order is Ready for Production when:

        • Not delivered
        • Remaining work exists
        • SAP user status indicates production readiness
    """

    if is_delivered(order):
        return False

    if remaining_minutes(order) <= 0:
        return False

    if not is_ready_status(order):
        return False

    return True


def is_awaiting_picking(order: Dict) -> bool:
    """
    Orders waiting for the warehouse.

    They still have work remaining,
    but have not yet reached PREP / COMP PREP / COMP.
    """

    if is_delivered(order):
        return False

    if remaining_minutes(order) <= 0:
        return False

    return not is_ready_status(order)


def production_state(order: Dict) -> str:
    """
    Returns one of:

        READY
        AWAITING_PICKING
        COMPLETE
    """

    if is_delivered(order):
        return "COMPLETE"

    if remaining_minutes(order) <= 0:
        return "COMPLETE"

    if is_ready_status(order):
        return "READY"

    return "AWAITING_PICKING"
