"""
Langfuse observability service — wraps the Langfuse SDK client.

Provides helper methods for tracing LLM calls and recording user feedback.
Degrades gracefully (no-op) if Langfuse keys are not configured.
"""
import time
from typing import Any, Dict, List, Optional

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Singleton Langfuse client
# ---------------------------------------------------------------------------
_langfuse_client = None
_enabled = False

def _init_client():
    """Lazy-init the Langfuse client exactly once."""
    global _langfuse_client, _enabled

    public_key = getattr(config, "LANGFUSE_PUBLIC_KEY", None)
    secret_key = getattr(config, "LANGFUSE_SECRET_KEY", None)
    host = getattr(config, "LANGFUSE_HOST", None)

    if not public_key or not secret_key:
        logger.info("Langfuse keys not configured — tracing disabled.")
        _enabled = False
        return

    try:
        from langfuse import Langfuse
        kwargs: Dict[str, Any] = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            kwargs["host"] = host

        _langfuse_client = Langfuse(**kwargs)
        _enabled = True
        logger.info("Langfuse client initialised (host=%s)", host or "cloud")
    except Exception as exc:
        logger.warning("Failed to initialise Langfuse: %s", exc)
        _enabled = False


def get_client():
    """Return the singleton Langfuse client (or None)."""
    if _langfuse_client is None:
        _init_client()
    return _langfuse_client


def is_enabled() -> bool:
    """Whether Langfuse tracing is active."""
    if _langfuse_client is None:
        _init_client()
    return _enabled


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def create_trace(
    *,
    name: str = "llm-call",
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    input: Optional[Any] = None,
    output: Optional[Any] = None,
):
    """Create a new Langfuse trace and return it (or None if disabled)."""
    if not is_enabled():
        logger.debug("Langfuse disabled — skipping create_trace")
        return None
    try:
        kwargs = {
            "name": name,
            "session_id": session_id,
            "user_id": user_id,
            "metadata": metadata or {},
        }
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output

        trace = _langfuse_client.trace(**kwargs)
        logger.info("Langfuse trace created: name=%s session=%s user=%s input_set=%s", name, session_id, user_id, input is not None)
        return trace
    except Exception as exc:
        logger.warning("Langfuse create_trace failed: %s", exc)
        return None


def log_generation(
    trace,
    *,
    name: str = "gemini-chat",
    model: str = "",
    input_messages: Optional[List[Dict[str, str]]] = None,
    output: str = "",
    start_time: Optional[float] = None,
    usage: Optional[Dict[str, int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Log a generation span under an existing trace (or standalone)."""
    if not is_enabled():
        logger.debug("Langfuse disabled — skipping log_generation")
        return None

    try:
        from datetime import datetime, timezone

        # If no trace was provided, create an ad-hoc one
        parent = trace or _langfuse_client.trace(name="ad-hoc")

        # Convert epoch float → datetime (Langfuse v2 expects datetime objects)
        dt_start = None
        dt_end = None
        if start_time:
            dt_start = datetime.fromtimestamp(start_time, tz=timezone.utc)
            dt_end = datetime.now(tz=timezone.utc)

        # Convert input_messages list to a readable string so Langfuse UI
        # displays the full System Prompt + Conversation History clearly
        formatted_input = input_messages
        if input_messages and isinstance(input_messages, list):
            parts = []
            for msg in input_messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                parts.append(f"[{role}]:\n{content}")
            formatted_input = "\n\n".join(parts)

        gen = parent.generation(
            name=name,
            model=model,
            input=formatted_input,
            output=output,
            metadata=metadata or {},
            usage=usage,
            start_time=dt_start,
            end_time=dt_end,
        )
        gen.end()

        # Force-flush so events reach Langfuse immediately
        _langfuse_client.flush()
        logger.info(
            "Langfuse generation logged: name=%s model=%s input_len=%d output_len=%d",
            name, model, len(formatted_input or ""), len(output or ""),
        )
        return gen
    except Exception as exc:
        logger.warning("Langfuse log_generation failed: %s", exc, exc_info=True)
        return None


def log_score(
    *,
    trace_id: Optional[str] = None,
    name: str = "user-feedback",
    value: float = 1.0,
    comment: Optional[str] = None,
):
    """Record a score (e.g. user thumbs-up/down) against a trace."""
    if not is_enabled():
        return None
    try:
        return _langfuse_client.score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )
    except Exception as exc:
        logger.warning("Langfuse log_score failed: %s", exc)
        return None


def flush():
    """Flush any pending Langfuse events (call on shutdown)."""
    if _langfuse_client is not None:
        try:
            _langfuse_client.flush()
        except Exception:
            pass