"""Real calls to the Speechify API. Skipped unless SPEECHIFY_API_KEY is set.

Run with: SPEECHIFY_API_KEY=... pytest -m live
"""

from __future__ import annotations

import os
import wave

import pytest

from hermes_speechify.client import SpeechifyError
from hermes_speechify.provider import SpeechifyTTSProvider

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("SPEECHIFY_API_KEY"), reason="SPEECHIFY_API_KEY not set"),
]


@pytest.fixture
def provider(monkeypatch):
    from hermes_speechify import provider as mod

    monkeypatch.setattr(mod, "get_env", lambda name: os.getenv(name, ""))
    monkeypatch.setattr(mod, "speechify_config", lambda: {})
    return SpeechifyTTSProvider()


def test_live_mp3(provider, tmp_path):
    out = provider.synthesize("Hello from Speechify and Hermes.", str(tmp_path / "a.mp3"))
    with open(out, "rb") as fh:
        data = fh.read()
    assert len(data) > 1000
    assert data[:3] == b"ID3" or data[:2] == b"\xff\xf3"


def test_live_ogg_is_opus(provider, tmp_path):
    out = provider.synthesize("Voice bubble test.", str(tmp_path / "a.ogg"), format="ogg")
    with open(out, "rb") as fh:
        head = fh.read(64)
    assert head.startswith(b"OggS") and b"OpusHead" in head


def test_live_wav(provider, tmp_path):
    out = provider.synthesize("Wave test.", str(tmp_path / "a.wav"), format="wav")
    with wave.open(out) as w:
        assert w.getframerate() == 24000 and w.getnframes() > 2400


def test_live_pcm_stream(provider):
    pcm = b"".join(provider.stream("Streaming test.", format="pcm"))
    assert len(pcm) > 4800 and len(pcm) % 2 == 0


def test_live_voices(provider):
    voices = provider.fetch_voices()
    ids = {v["id"] for v in voices}
    assert "geffen_32" in ids
    assert len(voices) > 50  # more than one page at the default limit


def test_live_bad_voice(provider, tmp_path):
    with pytest.raises(SpeechifyError) as info:
        provider.synthesize("Hi", str(tmp_path / "a.mp3"), voice="no_such_voice_xyz")
    assert info.value.code == "voice_not_found"


def test_live_bad_key(monkeypatch, tmp_path):
    from hermes_speechify import provider as mod

    monkeypatch.setattr(mod, "get_env", lambda name: "not-a-real-key" if "KEY" in name else "")
    monkeypatch.setattr(mod, "speechify_config", lambda: {})
    with pytest.raises(SpeechifyError) as info:
        SpeechifyTTSProvider().synthesize("Hi", str(tmp_path / "a.mp3"))
    assert info.value.status == 401
