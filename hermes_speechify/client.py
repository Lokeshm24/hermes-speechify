"""Small HTTP client for the Speechify text-to-speech API.

Plain ``requests`` on purpose: Hermes already ships it, the surface we need is
two endpoints, and it keeps the plugin free of extra dependencies.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests

from . import __version__

DEFAULT_BASE_URL = "https://api.speechify.ai"

# Pinned API version. From 2026-09-30 ``pcm_16000`` is real 16 kHz audio and
# ``GET /v1/voices`` is paged. Pinning keeps behaviour stable no matter which
# default the workspace has stored.
API_VERSION = "2026-09-30"

# The streaming endpoint accepts up to 20,000 characters per request.
MAX_INPUT_CHARS = 20000

_VOICES_PAGE_LIMIT = 200
_VOICES_MAX_PAGES = 50  # guard against a cursor loop; 10,000 voices is plenty


class SpeechifyError(RuntimeError):
    """A Speechify API call failed. The message is safe to show to users."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id


def _error_from_response(response: requests.Response) -> SpeechifyError:
    """Turn Speechify's error envelope into a readable exception.

    The envelope is ``{"error": {"code", "message"}, "request_id"}``. The API
    key is never part of it, so the message is safe to log.
    """
    code = message = request_id = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            message = err.get("message")
        elif isinstance(err, str):
            message = err
        request_id = body.get("request_id")
    if not message:
        message = (response.text or "").strip()[:300] or response.reason or "no details"
    request_id = request_id or response.headers.get("Speechify-Request-Id")

    status = response.status_code
    hint = ""
    if status == 401:
        hint = " Check SPEECHIFY_API_KEY (create one at https://console.speechify.ai)."
    elif code == "voice_not_found":
        hint = " Run `hermes speechify voices` to see the voices your key can use."
    elif status == 402:
        hint = " Your Speechify workspace is out of credits."

    label = f"HTTP {status}" + (f" {code}" if code else "")
    suffix = f" (request id {request_id})" if request_id else ""
    return SpeechifyError(
        f"Speechify API error ({label}): {message}{hint}{suffix}",
        status=status,
        code=code,
        request_id=request_id,
    )


class SpeechifyClient:
    """Stateless client. Each call opens its own request, so it is thread safe."""

    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0):
        if not api_key:
            raise SpeechifyError(
                "SPEECHIFY_API_KEY is not set. Create a key at https://console.speechify.ai "
                "and add it to ~/.hermes/.env"
            )
        self._api_key = api_key
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout

    def _headers(self, **extra: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Speechify-Version": API_VERSION,
            "User-Agent": f"hermes-speechify/{__version__}",
        }
        headers.update(extra)
        return headers

    def stream(
        self,
        text: str,
        *,
        voice_id: str,
        model: str | None,
        output_format: str,
        language: str | None = None,
        options: dict[str, Any] | None = None,
        chunk_size: int = 4096,
    ) -> Iterator[bytes]:
        """``POST /v1/audio/stream`` and yield audio bytes as they arrive.

        Errors are raised before the first chunk is yielded, so a caller never
        writes an error body into an audio file.
        """
        payload: dict[str, Any] = {
            "input": text,
            "voice_id": voice_id,
            "output_format": output_format,
        }
        if model:
            payload["model"] = model
        if language:
            payload["language"] = language
        if options:
            payload["options"] = options

        try:
            response = requests.post(
                f"{self._base_url}/v1/audio/stream",
                headers=self._headers(**{"Content-Type": "application/json"}),
                json=payload,
                timeout=self._timeout,
                stream=True,
            )
        except requests.RequestException as exc:
            raise SpeechifyError(f"Could not reach the Speechify API: {exc}") from exc

        with response:
            if response.status_code != 200:
                raise _error_from_response(response)
            content_type = response.headers.get("Content-Type", "")
            if content_type.startswith("application/json"):
                raise _error_from_response(response)
            try:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        yield chunk
            except requests.RequestException as exc:
                raise SpeechifyError(f"Speechify audio stream was cut off: {exc}") from exc

    def list_voices(
        self,
        *,
        model: str | None = None,
        locale: str | None = None,
        voice_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /v1/voices``, following ``next_cursor`` until ``has_more`` is false."""
        params: dict[str, Any] = {"limit": _VOICES_PAGE_LIMIT}
        if model:
            params["model"] = model
        if locale:
            params["locale"] = locale
        if voice_type:
            params["type"] = voice_type

        voices: list[dict[str, Any]] = []
        for _ in range(_VOICES_MAX_PAGES):
            try:
                response = requests.get(
                    f"{self._base_url}/v1/voices",
                    headers=self._headers(Accept="application/json"),
                    params=dict(params),
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                raise SpeechifyError(f"Could not reach the Speechify API: {exc}") from exc
            if response.status_code != 200:
                raise _error_from_response(response)
            body = response.json()
            # A short or empty page is not the end; only has_more says so.
            if isinstance(body, list):  # very old API shape, kept as a fallback
                voices.extend(v for v in body if isinstance(v, dict))
                break
            voices.extend(v for v in body.get("voices") or [] if isinstance(v, dict))
            cursor = body.get("next_cursor")
            if not body.get("has_more") or not cursor:
                break
            params["cursor"] = cursor
        return voices
