"""``hermes speechify ...`` terminal commands."""

from __future__ import annotations

import argparse
import sys
import tempfile
from typing import Any

from .client import SpeechifyError


def setup(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="speechify_command")

    voices = sub.add_parser("voices", help="List the Speechify voices your API key can use")
    voices.add_argument(
        "--model", help="Only voices for this model (default: your configured model)"
    )
    voices.add_argument("--locale", help="Only voices for this locale, e.g. en or en-US")
    voices.add_argument("--search", help="Only voices whose id or name contains this text")

    say = sub.add_parser("say", help="Speak a line through Speechify and save it to a file")
    say.add_argument("text", help="What to say")
    say.add_argument("--voice", help="Voice id (default: your configured voice)")
    say.add_argument("--model", help="Model id (default: your configured model)")
    say.add_argument("--format", default="mp3", choices=["mp3", "ogg", "wav"])
    say.add_argument("--out", help="Output file (default: a temp file)")


def _provider():
    from .provider import SpeechifyTTSProvider

    return SpeechifyTTSProvider()


def _print_voices(voices: list[dict[str, Any]]) -> None:
    if not voices:
        print("No voices matched.")
        return
    width = max(len(str(v["id"])) for v in voices)
    for v in sorted(voices, key=lambda v: (v.get("language", ""), str(v["id"]))):
        extra = " (your clone)" if v.get("type") == "personal" else ""
        print(
            f"{v['id']:<{width}}  {v.get('language', ''):<6} {v.get('gender', ''):<14} "
            f"{v.get('display', '')}{extra}"
        )
    print(f"\n{len(voices)} voices. Set one with `tts.speechify.voice` in ~/.hermes/config.yaml.")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "speechify_command", None)
    provider = _provider()
    try:
        if command == "voices":
            voices = provider.fetch_voices(model=args.model, locale=args.locale)
            if args.search:
                needle = args.search.lower()
                voices = [
                    v
                    for v in voices
                    if needle in str(v["id"]).lower() or needle in str(v.get("display", "")).lower()
                ]
            _print_voices(voices)
            return 0
        if command == "say":
            out = args.out or tempfile.mkstemp(prefix="speechify_", suffix=f".{args.format}")[1]
            path = provider.synthesize(
                args.text, out, voice=args.voice, model=args.model, format=args.format
            )
            print(path)
            return 0
    except (SpeechifyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Usage: hermes speechify {voices,say} --help", file=sys.stderr)
    return 2
