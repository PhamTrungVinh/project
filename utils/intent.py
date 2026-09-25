import re

_STANDALONE_PLEASANTRIES = {
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "goodbye", "bye", "thank you", "thanks", "ok", "okay",
    "xin chao", "xin chào", "chao", "chào", "tam biet", "tạm biệt",
    "cam on", "cảm ơn", "okela",
}


def is_standalone_pleasantry(text: str) -> bool:
    """Return true only for a short greeting, farewell, thanks, or acknowledgement."""
    normalized = re.sub(r"[^\w\sÀ-ỹ]", "", text.casefold()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in _STANDALONE_PLEASANTRIES


def explicit_ticket_and_booking_request(text: str) -> bool:
    """Recognize clear combined actions if the router omits one capability."""
    query = text.casefold()
    ticket_action = re.search(
        r"\b(?:create|open|submit|track|check|update|change|resolve|cancel|view)\s+"
        r"(?:(?:a|an|my|the)\s+)?(?:support\s+)?ticket\b",
        query,
    )
    booking_action = re.search(
        r"\b(?:make|create|schedule|cancel|update|reschedule|track|check|view)\s+"
        r"(?:(?:a|an|my|the)\s+)?booking\b"
        r"|\b(?:book|reserve)\s+(?:(?:a|the)\s+)?(?:meeting\s+)?room\b",
        query,
    )
    return bool(ticket_action and booking_action)
