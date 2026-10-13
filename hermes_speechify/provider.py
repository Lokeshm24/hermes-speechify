"""Speechify text-to-speech provider for Hermes Agent."""

from __future__ import annotations

import logging
import threading
import time
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from agent.tts_provider import TTSProvider

from .client import DEFAULT_BASE_URL, SpeechifyClient, SpeechifyError
from .config import get_env, positive_float, speechify_config, str_setting

logger = logging.getLogger(__name__)

API_KEY_ENV = "SPEECHIFY_API_KEY"
BASE_URL_ENV = "SPEECHIFY_BASE_URL"

DEFAULT_VOICE = "geffen_32"
DEFAULT_MODEL = "simba-3.2"  # English, lowest latency
MULTILINGUAL_MODEL = "simba-3.0"  # English + de, es, fr, it, pt

# Raw PCM for Hermes's streaming speaker: 16-bit little endian mono.
PCM_SAMPLE_RATE = 24000

# Hermes format name -> (Speechify output_format, file extension we write).
# ogg_24000 is Opus in an Ogg container, which is what voice bubbles need.
_FORMATS: dict[str, tuple[str, str]] = {
    "mp3": ("mp3_24000_128", "mp3"),
    "ogg": ("ogg_24000", "ogg"),
    "opus": ("ogg_24000", "ogg"),
    "wav": (f"pcm_{PCM_SAMPLE_RATE}", "wav"),
    "flac": (f"pcm_{PCM_SAMPLE_RATE}", "wav"),  # no FLAC on the API; lossless WAV is closest
}

_MODELS = [
    {
        "id": "simba-3.2",
        "display": "Simba 3.2 (English, lowest latency, most expressive)",
    },
    {
        "id": "simba-3.0",
        "display": "Simba 3.0 (English, German, Spanish, French, Italian, Portuguese)",
    },
]

_VOICE_CACHE_SECONDS = 600


def _rate_percent(speed: float | None) -> str | None:
    """Map Hermes's speed multiplier to an SSML prosody rate, or None for normal speed."""
    if speed is None:
        return None
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        return None
    speed = min(max(speed, 0.5), 4.0)  # Speechify accepts -50% and up
    percent = round((speed - 1.0) * 100)
    if percent == 0:
        return None
    return f"{percent:+d}%"


def _looks_like_ssml(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("<speak") and stripped.endswith("</speak>")


def build_input(text: str, speed: float | None) -> str:
    """Plain text goes as is (the API escapes it). A speed change wraps it in SSML."""
    rate = _rate_percent(speed)
    if rate is None or _looks_like_ssml(text):
        return text
    return f'<speak><prosody rate="{rate}">{escape(text.strip())}</prosody></speak>'


class SpeechifyTTSProvider(TTSProvider):
    """Speechify streaming TTS over plain HTTP (no Speechify SDK needed)."""

    # Opt into Hermes's low-latency streaming speaker (Hermes 0.21.6+). Older
    # builds ignore these and speak sentence by sentence through synthesize().
    streams_pcm = True
    stream_sample_rate = PCM_SAMPLE_RATE

    def __init__(self) -> None:
        self._voice_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._voice_lock = threading.Lock()

    # ---- identity -------------------------------------------------------

    @property
    def name(self) -> str:
        return "speechify"

    @property
    def display_name(self) -> str:
        return "Speechify"

    @property
    def voice_compatible(self) -> bool:
        # ogg output is already Opus; other formats are converted by Hermes.
        return True

    def is_available(self) -> bool:
        # No network here: Hermes calls this on every picker paint.
        return bool(get_env(API_KEY_ENV))

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Speechify",
            "badge": "paid",
            "tag": "Simba 3 streaming voices, low latency",
            "env_vars": [
                {
                    "key": API_KEY_ENV,
                    "prompt": "Speechify API key",
                    "url": "https://platform.speechify.ai/signup?utm_source=hermes&utm_medium=integration&utm_campaign=hermes-agent",
                }
            ],
        }

    # ---- catalog --------------------------------------------------------

    def list_models(self) -> list[dict[str, Any]]:
        return [dict(m) for m in _MODELS]

    def default_model(self) -> str:
        return DEFAULT_MODEL

    def default_voice(self) -> str:
        return DEFAULT_VOICE

    def list_voices(self) -> list[dict[str, Any]]:
        """Voices this key can use with the configured model. Cached for 10 minutes.

        Returns ``[]`` (and logs) on failure so a picker never crashes.
        """
        try:
            return self.fetch_voices()
        except SpeechifyError as exc:
            logger.warning("Speechify voice list failed: %s", exc)
            return []

    def fetch_voices(
        self, *, model: str | None = None, locale: str | None = None, any_model: bool = False
    ) -> list[dict[str, Any]]:
        """Like :meth:`list_voices` but raises :class:`SpeechifyError` on failure.

        Filters to ``model`` (default: the configured model) unless ``any_model``.
        """
        config = speechify_config()
        if any_model:
            model = None
        elif not model:
            model = str_setting(config, "model") or DEFAULT_MODEL
        cache_key = f"{model}|{locale or ''}"
        with self._voice_lock:
            cached = self._voice_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < _VOICE_CACHE_SECONDS:
                return [dict(v) for v in cached[1]]

        raw = self._client(config).list_voices(model=model, locale=locale)
        voices = [
            {
                "id": v.get("id"),
                "display": v.get("display_name") or v.get("id"),
                "language": v.get("locale") or "",
                "gender": v.get("gender") or "",
                "preview_url": v.get("preview_audio") or "",
                "type": v.get("type") or "",
                "models": [
                    m.get("name")
                    for m in v.get("models") or []
                    if isinstance(m, dict) and m.get("name")
                ],
            }
            for v in raw
            if v.get("id")
        ]
        with self._voice_lock:
            self._voice_cache[cache_key] = (time.monotonic(), voices)
        return [dict(v) for v in voices]

    # ---- synthesis ------------------------------------------------------

    def _client(self, config: dict[str, Any]) -> SpeechifyClient:
        base_url = str_setting(config, "base_url") or get_env(BASE_URL_ENV) or DEFAULT_BASE_URL
        timeout = positive_float(config.get("timeout"), 60.0)
        return SpeechifyClient(get_env(API_KEY_ENV), base_url=base_url, timeout=timeout)

    def _resolve(
        self, config: dict[str, Any], voice: str | None, model: str | None
    ) -> tuple[str, str, str | None]:
        voice_id = voice or str_setting(config, "voice") or DEFAULT_VOICE
        language = str_setting(config, "language")
        default_model = DEFAULT_MODEL
        if language and not language.lower().startswith("en"):
            default_model = MULTILINGUAL_MODEL  # simba-3.2 is English only
        resolved_model = model or str_setting(config, "model") or default_model
        return voice_id, resolved_model, language

    def _options(self, config: dict[str, Any]) -> dict[str, Any]:
        options: dict[str, Any] = {}
        for key in ("text_normalization", "loudness_normalization"):
            if isinstance(config.get(key), bool):
                options[key] = config[key]
        return options

    def _audio(
        self,
        text: str,
        *,
        output_format: str,
        voice: str | None,
        model: str | None,
        speed: float | None,
    ) -> Iterator[bytes]:
        if not text or not text.strip():
            raise ValueError("Speechify TTS needs some text to speak")
        config = speechify_config()
        voice_id, resolved_model, language = self._resolve(config, voice, model)
        if speed is None and config.get("speed") is not None:
            speed = positive_float(config.get("speed"), 1.0)
        return self._client(config).stream(
            build_input(text, speed),
            voice_id=voice_id,
            model=resolved_model,
            output_format=output_format,
            language=language,
            options=self._options(config),
        )

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: str | None = None,
        model: str | None = None,
        speed: float | None = None,
        format: str = "mp3",
        **extra: Any,
    ) -> str:
        requested = str(format or Path(output_path).suffix.lstrip(".") or "mp3").lower()
        output_format, extension = _FORMATS.get(requested, _FORMATS["mp3"])

        target = Path(output_path)
        if target.suffix.lstrip(".").lower() != extension:
            target = target.with_suffix(f".{extension}")
        target.parent.mkdir(parents=True, exist_ok=True)

        chunks = self._audio(
            text, output_format=output_format, voice=voice, model=model, speed=speed
        )
        try:
            if extension == "wav":
                pcm = b"".join(chunks)
                with wave.open(str(target), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(PCM_SAMPLE_RATE)
                    wav.writeframes(pcm)
            else:
                with open(target, "wb") as handle:
                    for chunk in chunks:
                        handle.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise

        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise SpeechifyError("Speechify returned no audio")
        return str(target)

    def stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        model: str | None = None,
        format: str = "opus",
        **extra: Any,
    ) -> Iterator[bytes]:
        """Yield audio as it is generated.

        ``format="pcm"`` gives raw 24 kHz 16-bit mono PCM for Hermes's speaker.
        ``opus``/``ogg`` give Ogg Opus, ``mp3`` gives MP3. Safe to call from
        several threads at once.
        """
        requested = str(format or "opus").lower()
        if requested == "pcm":
            output_format = f"pcm_{PCM_SAMPLE_RATE}"
        elif requested in ("opus", "ogg"):
            output_format = "ogg_24000"
        else:
            output_format = _FORMATS.get(requested, _FORMATS["mp3"])[0]
            if output_format.startswith("pcm_"):
                output_format = f"pcm_{PCM_SAMPLE_RATE}"
        yield from self._audio(
            text,
            output_format=output_format,
            voice=voice,
            model=model,
            speed=extra.get("speed"),
        )
