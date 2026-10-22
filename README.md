# Speechify for Hermes Agent

Give [Hermes Agent](https://github.com/NousResearch/hermes-agent) a Speechify voice.

This plugin adds Speechify as a text-to-speech provider. Once it is on, Hermes
speaks its replies with Speechify's Simba models (Simba 3.5 by default, 48 languages): in CLI voice mode, in
Hermes Desktop, and as voice notes on Telegram, Discord, WhatsApp and the other
gateway platforms.

- **Low latency.** Audio streams from `POST /v1/audio/stream`, and in voice mode
  Hermes starts playing while the rest of the sentence is still being made
  (Hermes 0.21.6 or newer).
- **Voice bubbles that just work.** Ogg output is Opus, which Telegram and
  Discord play inline.
- **Every voice your key can use**, including your own cloned voices.
- No extra Python packages. It uses `requests`, which Hermes already ships.

## Install

You need a Speechify API key. Create one at
[platform.speechify.ai](https://platform.speechify.ai/signup?utm_source=github&utm_medium=readme&utm_campaign=hermes-agent).

```bash
hermes plugins install Speechify-AI/hermes-speechify
hermes plugins enable speechify
```

Hermes asks for `SPEECHIFY_API_KEY` during install and saves it to
`~/.hermes/.env`. To set it yourself:

```bash
echo 'SPEECHIFY_API_KEY=your-key-here' >> ~/.hermes/.env
```

## Turn it on

In `~/.hermes/config.yaml`:

```yaml
tts:
  provider: speechify
```

That's all you need. Hermes now speaks with the `geffen_32` voice on `simba-3.5`.
Restart Hermes (or the gateway) after changing the config.

## Pick a voice

List every voice your key can use:

```bash
hermes speechify voices
hermes speechify voices --locale en-GB
hermes speechify voices --model simba-3.5
hermes speechify voices --search oliver
```

Hear one before you choose it:

```bash
hermes speechify say "Hi, I'm your new voice." --voice geffen_32
```

This prints the path of the audio file it wrote.

Then set it:

```yaml
tts:
  provider: speechify
  speechify:
    voice: geffen_32
```

Your own cloned voices show up in the list too, marked "(your clone)".

## All settings

Everything goes under `tts.speechify` and is optional.

```yaml
tts:
  provider: speechify
  output_format: mp3          # mp3 (default), ogg, opus or wav
  speed: 1.0                  # 0.5 to 4.0, sent as SSML <prosody rate>
  speechify:
    voice: geffen_32          # any id from `hermes speechify voices`
    model: simba-3.5          # simba-3.5 (default), simba-3.2 (English only) or simba-3.0
    language: en-US           # optional; set it when the text is not in the voice's own language
    text_normalization: true  # optional; spell out numbers, dates, units
    loudness_normalization: false
    timeout: 60               # seconds
    max_text_length: 4000     # Hermes splits longer replies into chunks (API max 20000)
```

Hermes's shared `tts.voice` and `tts.model` keys also work, and win over the
`tts.speechify` ones.

### Models

| Model | Languages | Notes |
| --- | --- | --- |
| `simba-3.5` (default) | 48 languages, English included | Works with every voice. First model with pronunciation support |
| `simba-3.2` | English | English only, lowest latency |
| `simba-3.0` | English, German, Spanish, French, Italian, Portuguese | Older model with six languages |

`simba-3.5` is the default for every language, so the plugin never switches
models for you. Set `language` (for example `fr-FR` or `ja`) when the text is
not in the voice's own language. `simba-3.2` refuses non-English voices.

### Audio formats

| `output_format` | What you get |
| --- | --- |
| `mp3` | MP3, 24 kHz, 128 kbps |
| `ogg` / `opus` | Opus in Ogg, 24 kHz. Plays as a voice bubble with no conversion |
| `wav` | 16-bit PCM WAV, 24 kHz |
| `flac` | Not offered by the API. You get WAV instead |

For live voice mode the plugin streams raw 24 kHz PCM to Hermes's speaker.

**Using Hermes on Telegram, Discord or WhatsApp?** Set `output_format: ogg`.
Speechify then sends Opus directly, so replies arrive as voice bubbles even
when ffmpeg is not installed. With `mp3`, Hermes needs ffmpeg to convert them.

## How it talks to Speechify

- `POST https://api.speechify.ai/v1/audio/stream` to make speech.
- `GET https://api.speechify.ai/v1/voices` to list voices (only when you ask for them).
- Every request sends `Speechify-Version: 2026-09-30`, so the plugin behaves the
  same no matter which API version your workspace has stored.

What leaves your machine: the text Hermes speaks, your API key, and the voice
and model you picked. They go to `api.speechify.ai` (or the `base_url` you set)
and nowhere else. Speechify bills synthesis to your workspace by character.
There is no telemetry.

## Troubleshooting

| You see | Do this |
| --- | --- |
| `SPEECHIFY_API_KEY is not set` | Add the key to `~/.hermes/.env` |
| `HTTP 401 unauthorized` | The key is wrong or revoked. Make a new one |
| `HTTP 403 insufficient_scope` | The key cannot use text-to-speech. Make a key with audio access |
| `HTTP 404 voice_not_found` | Run `hermes speechify voices` and pick an id from the list |
| `HTTP 400` naming the model | `simba-3.2` is English only. Use `simba-3.5` for other languages |
| `HTTP 402` | The workspace is out of credits |
| Hermes still uses Edge | Check `hermes plugins list` shows `speechify` enabled, then restart |

Every error includes Speechify's request id. Include it when you contact
Speechify support.

## Development

```bash
git clone https://github.com/NousResearch/hermes-agent   # for the real base class
uv venv && uv pip install -e . pytest ruff
HERMES_SRC=./hermes-agent bash scripts/install-hermes-contract.sh
uv run pytest                                  # unit tests, no network
SPEECHIFY_API_KEY=... uv run pytest -m live    # real API calls
hermes plugins validate .                      # the catalog admission check
```

## License

MIT. See [LICENSE](LICENSE).
