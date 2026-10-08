from __future__ import annotations

import argparse

from conftest import FakeResponse

import hermes_speechify
from hermes_speechify import cli
from hermes_speechify.provider import SpeechifyTTSProvider


def _voice(voice_id, locale="en-US", vtype="shared"):
    return {
        "id": voice_id,
        "display_name": voice_id.title(),
        "locale": locale,
        "gender": "male",
        "models": [{"name": "simba-3.2", "languages": []}],
        "preview_audio": f"https://cdn.test/{voice_id}.mp3",
        "type": vtype,
    }


def test_list_voices_follows_cursor(fake_env, http):
    http["queue"].extend(
        [
            FakeResponse(
                payload={"voices": [_voice("alec")], "next_cursor": "c1", "has_more": True}
            ),
            # a short (even empty) page is not the end of the list
            FakeResponse(payload={"voices": [], "next_cursor": "c2", "has_more": True}),
            FakeResponse(
                payload={
                    "voices": [_voice("mine", vtype="personal")],
                    "next_cursor": None,
                    "has_more": False,
                }
            ),
        ]
    )

    voices = SpeechifyTTSProvider().list_voices()

    assert [v["id"] for v in voices] == ["alec", "mine"]
    assert voices[0] == {
        "id": "alec",
        "display": "Alec",
        "language": "en-US",
        "gender": "male",
        "preview_url": "https://cdn.test/alec.mp3",
        "type": "shared",
        "models": ["simba-3.2"],
    }
    calls = http["calls"]
    assert [c["params"].get("cursor") for c in calls] == [None, "c1", "c2"]
    assert all(c["params"]["limit"] == 200 for c in calls)
    assert all(c["params"]["model"] == "simba-3.2" for c in calls)
    assert all(c["headers"]["Speechify-Version"] == "2026-09-30" for c in calls)


def test_list_voices_is_cached(fake_env, http):
    http["queue"].append(FakeResponse(payload={"voices": [_voice("alec")], "has_more": False}))
    p = SpeechifyTTSProvider()
    assert p.list_voices() == p.list_voices()
    assert len(http["calls"]) == 1


def test_list_voices_never_raises(fake_env, http):
    http["queue"].append(
        FakeResponse(401, payload={"error": {"code": "unauthorized", "message": "no"}})
    )
    assert SpeechifyTTSProvider().list_voices() == []


def test_register_wires_provider_and_cli():
    seen = {}

    class Ctx:
        def register_tts_provider(self, provider):
            seen["tts"] = provider

        def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
            seen["cli"] = (name, setup_fn, handler_fn)

    hermes_speechify.register(Ctx())

    assert isinstance(seen["tts"], SpeechifyTTSProvider)
    assert seen["cli"][0] == "speechify"


def test_register_works_without_cli_hook():
    seen = {}

    class Ctx:
        def register_tts_provider(self, provider):
            seen["tts"] = provider

    hermes_speechify.register(Ctx())
    assert "tts" in seen


def _parse(*argv):
    parser = argparse.ArgumentParser()
    cli.setup(parser)
    return parser.parse_args(list(argv))


def test_cli_voices(fake_env, http, capsys):
    http["queue"].append(
        FakeResponse(
            payload={"voices": [_voice("alec", "en-GB"), _voice("geffen_32")], "has_more": False}
        )
    )
    assert cli.handle(_parse("voices", "--search", "gef")) == 0
    out = capsys.readouterr().out
    assert "geffen_32" in out and "alec" not in out
    # the CLI lists every model unless --model is given
    assert "model" not in http["calls"][0]["params"]


def test_cli_reports_errors(fake_env, http, capsys):
    http["queue"].append(
        FakeResponse(401, payload={"error": {"code": "unauthorized", "message": "no"}})
    )
    assert cli.handle(_parse("voices")) == 1
    assert "HTTP 401" in capsys.readouterr().err
