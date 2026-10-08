from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeResponse:
    """Enough of ``requests.Response`` for the client."""

    def __init__(
        self,
        status_code: int = 200,
        *,
        chunks: list[bytes] | None = None,
        payload: Any = None,
        headers: dict[str, str] | None = None,
        reason: str = "",
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks or []
        self._payload = payload
        self.headers = headers or {}
        self.reason = reason
        self.closed = False

    @property
    def text(self) -> str:
        return json.dumps(self._payload) if self._payload is not None else ""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def iter_content(self, chunk_size: int = 1):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False


@pytest.fixture
def fake_env(monkeypatch):
    """Point the provider at a fake key and an empty config section."""
    from hermes_speechify import provider

    state = {"env": {"SPEECHIFY_API_KEY": "test-key"}, "config": {}}
    monkeypatch.setattr(provider, "get_env", lambda name: state["env"].get(name, ""))
    monkeypatch.setattr(provider, "speechify_config", lambda: state["config"])
    return state


@pytest.fixture
def http(monkeypatch):
    """Capture outgoing requests and return queued responses."""
    from hermes_speechify import client

    calls: list[dict[str, Any]] = []
    queue: list[FakeResponse] = []

    def fake(method):
        def _call(url, **kwargs):
            calls.append({"method": method, "url": url, **kwargs})
            return queue.pop(0)

        return _call

    monkeypatch.setattr(client.requests, "post", fake("POST"))
    monkeypatch.setattr(client.requests, "get", fake("GET"))
    return {"calls": calls, "queue": queue}
