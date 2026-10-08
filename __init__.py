"""Directory-plugin entry point for Hermes Agent."""

try:
    from .hermes_speechify import register
except ImportError:  # imported directly by tests or build tools, not by Hermes
    from hermes_speechify import register

__all__ = ["register"]
