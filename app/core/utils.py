"""
Shared utility functions.
"""
from app.core.constants import PROVIDER_ALIASES, SUPPORTED_PROVIDERS

def normalize_provider(provider: str) -> str:
    """
    Normalizes provider names and preserves 'unknown' until user selects in chat.
    """
    p = (provider or "").strip().lower()
    if not p:
        return "unknown"

    p = PROVIDER_ALIASES.get(p, p)
    if p in SUPPORTED_PROVIDERS:
        return p
    return "unknown"
