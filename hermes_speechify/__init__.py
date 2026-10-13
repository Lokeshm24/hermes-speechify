"""Speechify text-to-speech for Hermes Agent."""

from __future__ import annotations

__version__ = "0.1.1"


def register(ctx) -> None:
    """Hermes plugin entry point."""
    from . import cli
    from .provider import SpeechifyTTSProvider

    ctx.register_tts_provider(SpeechifyTTSProvider())

    register_cli = getattr(ctx, "register_cli_command", None)
    if callable(register_cli):
        register_cli(
            "speechify",
            "Speechify voices and a quick test",
            cli.setup,
            cli.handle,
            description="List Speechify voices or speak a test line.",
        )


__all__ = ["__version__", "register"]
