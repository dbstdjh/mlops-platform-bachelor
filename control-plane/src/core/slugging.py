import re
import unicodedata


def slugify(value: str) -> str:
    """Convert a display name into a URL-safe, human-readable slug."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug or "resource"


def slug_candidate(base_slug: str, index: int) -> str:
    """Return the base slug or a deterministic suffixed variant."""
    if index <= 1:
        return base_slug
    return f"{base_slug}-{index}"
