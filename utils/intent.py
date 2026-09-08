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
