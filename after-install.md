# Speechify installed

Turn it on and pick it as your voice in `~/.hermes/config.yaml`:

```yaml
tts:
  provider: speechify
  speechify:
    voice: geffen_32
    model: simba-3.5
```

Run `hermes speechify voices` to see every voice your key can use, then restart Hermes.
