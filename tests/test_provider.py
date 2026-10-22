from __future__ import annotations

import wave

import pytest
from conftest import FakeResponse

from hermes_speechify.client import API_VERSION, SpeechifyError
from hermes_speechify.provider import SpeechifyTTSProvider, build_input
from hermes_speechify import __version__


def test_identity_and_catalog():
    p = SpeechifyTTSProvider()
    assert p.name == "speechify"
    assert p.display_name == "Speechify"
    assert p.default_voice() == "geffen_32"
    assert p.default_model() == "simba-3.5"
    assert [m["id"] for m in p.list_models()] == ["simba-3.5", "simba-3.2", "simba-3.0"]
    assert p.voice_compatible is True
    assert p.streams_pcm is True and p.stream_sample_rate == 24000
    schema = p.get_setup_schema()
    assert schema["env_vars"][0]["key"] == "SPEECHIFY_API_KEY"


def test_is_available_follows_key(fake_env):
    p = SpeechifyTTSProvider()
    assert p.is_available()
    fake_env["env"].clear()
    assert not p.is_available()


def test_synthesize_mp3_defaults(fake_env, http, tmp_path):
    http["queue"].append(
        FakeResponse(chunks=[b"ID3", b"audio"], headers={"Content-Type": "audio/mpeg"})
    )
    out = tmp_path / "reply.mp3"

    result = SpeechifyTTSProvider().synthesize("Hello there.", str(out))

    assert result == str(out)
    assert out.read_bytes() == b"ID3audio"
    call = http["calls"][0]
    assert call["url"] == "https://api.speechify.ai/v1/audio/stream"
    assert call["stream"] is True
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["headers"]["Speechify-Version"] == API_VERSION == "2026-09-30"
    assert call["headers"]["Speechify-Caller"] == "hermes-agent"
    assert call["headers"]["Speechify-Caller-Version"] == __version__
    assert call["json"] == {
        "input": "Hello there.",
        "voice_id": "geffen_32",
        "model": "simba-3.5",
        "output_format": "mp3_24000_128",
    }


def test_call_args_beat_config(fake_env, http, tmp_path):
    fake_env["config"].update({"voice": "config_voice", "model": "simba-3.0"})
    http["queue"].append(FakeResponse(chunks=[b"x"]))

    SpeechifyTTSProvider().synthesize(
        "Hi", str(tmp_path / "a.mp3"), voice="call_voice", model="simba-3.2"
    )

    body = http["calls"][0]["json"]
    assert body["voice_id"] == "call_voice"
    assert body["model"] == "simba-3.2"


def test_config_section_used(fake_env, http, tmp_path):
    fake_env["config"].update(
        {
            "voice": "config_voice",
            "language": "fr-FR",
            "base_url": "https://example.test/",
            "text_normalization": True,
            "timeout": 7,
        }
    )
    http["queue"].append(FakeResponse(chunks=[b"x"]))

    SpeechifyTTSProvider().synthesize("Bonjour", str(tmp_path / "a.mp3"))

    call = http["calls"][0]
    assert call["url"] == "https://example.test/v1/audio/stream"
    assert call["timeout"] == 7
    assert call["json"]["voice_id"] == "config_voice"
    assert call["json"]["language"] == "fr-FR"
    # simba-3.5 speaks every language, so a non-English language keeps the default model
    assert call["json"]["model"] == "simba-3.5"
    assert call["json"]["options"] == {"text_normalization": True}


def test_ogg_is_native_opus(fake_env, http, tmp_path):
    http["queue"].append(FakeResponse(chunks=[b"OggS"]))
    out = SpeechifyTTSProvider().synthesize("Hi", str(tmp_path / "a.ogg"), format="opus")
    assert out.endswith(".ogg")
    assert http["calls"][0]["json"]["output_format"] == "ogg_24000"


def test_wav_wraps_pcm(fake_env, http, tmp_path):
    pcm = b"\x01\x00" * 2400
    http["queue"].append(FakeResponse(chunks=[pcm[:100], pcm[100:]]))

    out = SpeechifyTTSProvider().synthesize("Hi", str(tmp_path / "a.wav"), format="wav")

    assert http["calls"][0]["json"]["output_format"] == "pcm_24000"
    with wave.open(out) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.readframes(w.getnframes()) == pcm


def test_unsupported_format_falls_back_and_fixes_extension(fake_env, http, tmp_path):
    http["queue"].append(FakeResponse(chunks=[b"\x00\x00"]))
    out = SpeechifyTTSProvider().synthesize("Hi", str(tmp_path / "a.flac"), format="flac")
    assert out.endswith(".wav")


def test_speed_becomes_ssml_prosody(fake_env, http, tmp_path):
    http["queue"].append(FakeResponse(chunks=[b"x"]))
    SpeechifyTTSProvider().synthesize("Fish & <chips>", str(tmp_path / "a.mp3"), speed=1.25)
    assert http["calls"][0]["json"]["input"] == (
        '<speak><prosody rate="+25%">Fish &amp; &lt;chips&gt;</prosody></speak>'
    )


def test_build_input_edges():
    assert build_input("plain", None) == "plain"
    assert build_input("plain", 1.0) == "plain"
    assert build_input("slow", 0.1) == '<speak><prosody rate="-50%">slow</prosody></speak>'
    ssml = "<speak>already <break time='1s'/> ssml</speak>"
    assert build_input(ssml, 1.5) == ssml


def test_empty_text_rejected(fake_env, tmp_path):
    with pytest.raises(ValueError):
        SpeechifyTTSProvider().synthesize("   ", str(tmp_path / "a.mp3"))


def test_missing_key_is_clear(fake_env, tmp_path):
    fake_env["env"].clear()
    with pytest.raises(SpeechifyError, match="SPEECHIFY_API_KEY is not set"):
        SpeechifyTTSProvider().synthesize("Hi", str(tmp_path / "a.mp3"))


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (
            401,
            {"error": {"code": "unauthorized", "message": "Unauthorized"}, "request_id": "r1"},
            "HTTP 401 unauthorized",
        ),
        (
            404,
            {
                "error": {"code": "voice_not_found", "message": "Voice not found."},
                "request_id": "r2",
            },
            "hermes speechify voices",
        ),
        (
            402,
            {"error": {"code": "payment_required", "message": "Insufficient Credits"}},
            "out of credits",
        ),
    ],
)
def test_api_errors_raise_and_leave_no_file(fake_env, http, tmp_path, status, payload, expected):
    http["queue"].append(
        FakeResponse(status, payload=payload, headers={"Content-Type": "application/json"})
    )
    out = tmp_path / "a.mp3"
    with pytest.raises(SpeechifyError, match=expected) as info:
        SpeechifyTTSProvider().synthesize("Hi", str(out))
    assert info.value.status == status
    assert "test-key" not in str(info.value)
    assert not out.exists()


def test_non_json_error_body(fake_env, http, tmp_path):
    http["queue"].append(FakeResponse(502, reason="Bad Gateway"))
    with pytest.raises(SpeechifyError, match="HTTP 502"):
        SpeechifyTTSProvider().synthesize("Hi", str(tmp_path / "a.mp3"))


def test_empty_audio_is_an_error(fake_env, http, tmp_path):
    http["queue"].append(FakeResponse(chunks=[]))
    out = tmp_path / "a.mp3"
    with pytest.raises(SpeechifyError, match="no audio"):
        SpeechifyTTSProvider().synthesize("Hi", str(out))
    assert not out.exists()


def test_stream_pcm_for_hermes_speaker(fake_env, http):
    http["queue"].append(FakeResponse(chunks=[b"\x00\x01", b"\x02\x03"]))

    chunks = list(SpeechifyTTSProvider().stream("Hi", format="pcm", voice="v", speed=None))

    assert chunks == [b"\x00\x01", b"\x02\x03"]
    body = http["calls"][0]["json"]
    assert body["output_format"] == "pcm_24000"
    assert body["voice_id"] == "v"


def test_stream_default_is_opus(fake_env, http):
    http["queue"].append(FakeResponse(chunks=[b"OggS"]))
    list(SpeechifyTTSProvider().stream("Hi"))
    assert http["calls"][0]["json"]["output_format"] == "ogg_24000"
