"""Privacy-safe comparisons for Phase 4.5 read-only shadow checks."""

from collections.abc import Mapping


TICKET_FIELDS = ("ticket_code", "content", "description", "status")
BOOKING_FIELDS = ("booking_code", "reason", "time", "note", "status")


def compare_record(local: object, remote: Mapping[str, object], fields: tuple[str, ...]) -> dict[str, tuple[object, object]]:
    """Return differing non-PII fields; callers never shadow-write mutations."""
    differences = {}
    for field in fields:
        local_value = getattr(local, field, None)
        if hasattr(local_value, "value"):
            local_value = local_value.value
        remote_value = remote.get(field)
        if str(local_value) != str(remote_value):
            differences[field] = (local_value, remote_value)
    return differences


def compare_ticket(local: object, remote: Mapping[str, object]) -> dict[str, tuple[object, object]]:
    return compare_record(local, remote, TICKET_FIELDS)


def compare_booking(local: object, remote: Mapping[str, object]) -> dict[str, tuple[object, object]]:
    return compare_record(local, remote, BOOKING_FIELDS)
