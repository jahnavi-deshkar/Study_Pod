import re


def normalize_roll(raw_roll):
    """Normalize a roster roll code (for example, ``m-1`` to ``M1``)."""
    return re.sub(r"[\s-]+", "", str(raw_roll or "")).upper()


def normalize_batch(raw_batch):
    """Map common shorthand to the two canonical DSP batch names."""
    value = re.sub(r"\s+", " ", str(raw_batch or "").strip()).casefold()
    if value in {"morning", "morning batch", "m", "morn"}:
        return "Morning Batch"
    if value in {"evening", "evening batch", "e", "eve"}:
        return "Evening Batch"
    return ""


def normalize_name(raw_name):
    """Normalize names and convert the common ``Last, First`` format."""
    value = " ".join(str(raw_name or "").split())
    if "," in value:
        last, first = (part.strip() for part in value.split(",", 1))
        value = f"{first} {last}".strip()
    return value.title()
