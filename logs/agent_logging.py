# Structured JSON logging for the GA4 analysis agent.
# Log file: agent.jsonl in this directory (override with AGENT_LOG_FILE).

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

_LOGGER_NAME = "logs.agent"
_tls = threading.local()

# Default log file next to this module
_DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "agent.jsonl"


def _resolve_log_file() -> Path:
    override = os.getenv("AGENT_LOG_FILE")
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_LOG_FILE.resolve()


def configure_agent_logging() -> None:
    """Attach stdout + file handlers (one JSON object per line). Idempotent per process."""
    log = logging.getLogger(_LOGGER_NAME)
    if log.handlers:
        return
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = logging.Formatter("%(message)s")

    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(fmt)
    log.addHandler(out)

    log_path = _resolve_log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)

    log.setLevel(level)
    log.propagate = False


def get_agent_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def begin_agent_trace() -> list[dict[str, Any]]:
    """Start collecting structured events for the current request (thread-local)."""
    buf: list[dict[str, Any]] = []
    _tls.agent_trace = buf
    return buf


def end_agent_trace() -> None:
    """Clear the per-request trace buffer."""
    if hasattr(_tls, "agent_trace"):
        delattr(_tls, "agent_trace")


def _emit(level: int, event: str, **fields: Any) -> None:
    log = get_agent_logger()
    payload: dict[str, Any] = {"event": event, **fields}
    trace = getattr(_tls, "agent_trace", None)
    if trace is not None:
        trace.append(dict(payload))
    line = json.dumps(payload, ensure_ascii=False, default=str)
    log.log(level, line)


def log_agent_event(event: str, **fields: Any) -> None:
    """Structured INFO log: one JSON object per line."""
    _emit(logging.INFO, event, **fields)


def log_agent_debug(event: str, **fields: Any) -> None:
    """Structured DEBUG log (e.g. full SQL)."""
    _emit(logging.DEBUG, event, **fields)


def log_agent_warning(event: str, **fields: Any) -> None:
    _emit(logging.WARNING, event, **fields)


def truncate_text(text: str | None, max_chars: int = 500) -> str | None:
    if text is None:
        return None
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def extract_usage_fields(message: Any) -> dict[str, Any]:
    """Pull token usage from an Anthropic message if present."""
    out: dict[str, Any] = {}
    usage = getattr(message, "usage", None)
    if usage is None:
        return out
    for attr in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        if hasattr(usage, attr):
            val = getattr(usage, attr, None)
            if val is not None:
                out[attr] = val
    return out
