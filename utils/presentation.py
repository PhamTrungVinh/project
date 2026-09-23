import re

def to_plain_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("**", "").replace("__", "").replace(chr(96), "")
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
