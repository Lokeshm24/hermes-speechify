"""Read the API key and the ``tts.speechify`` section from Hermes."""

from __future__ import annotations

import os
from typing import Any


def get_env(name: str) -> str:
    """Read a value from the process env or ``~/.hermes/.env`` (profile aware)."""
    try:
        from hermes_cli.config import get_env_value

        value = get_env_value(name)
    except (ImportError, RuntimeError):
        value = os.getenv(name)
    return str(value or "").strip()


def speechify_config() -> dict[str, Any]:
    """Return ``tts.speechify`` from the Hermes config, or ``{}``."""
    try:
        from hermes_cli.config import load_config

        config = load_config()
    except (ImportError, OSError, ValueError, TypeError):
        return {}
    tts = config.get("tts") if isinstance(config, dict) else None
    section = tts.get("speechify") if isinstance(tts, dict) else None
    return section if isinstance(section, dict) else {}


def str_setting(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def positive_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
