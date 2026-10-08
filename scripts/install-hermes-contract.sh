#!/usr/bin/env bash
# Put a Hermes Agent checkout into the current uv env so the tests can import
# the real TTSProvider base class. Set HERMES_SRC, or clone hermes-agent into
# ./hermes-agent first.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="${HERMES_SRC:-$root/hermes-agent}"

if [[ ! -f "$src/pyproject.toml" ]]; then
  echo "No Hermes checkout at $src. Clone https://github.com/NousResearch/hermes-agent there or set HERMES_SRC." >&2
  exit 1
fi

# Hermes only supports editable installs. Its core deps are not needed to
# import the provider base class, but hermes_cli.config needs its yaml pin.
yaml_pin="$(grep -oE 'ruamel\.yaml==[^"; ]+' "$src/pyproject.toml" | head -1)"
uv pip install -e "$src" --no-deps
uv pip install "$yaml_pin"
