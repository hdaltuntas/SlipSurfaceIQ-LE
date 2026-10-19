#!/usr/bin/env bash
# SlipSurface LE - Linux/macOS: sanal ortami kurar (ilk seferde) ve programi baslatir.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Sanal ortam olusturuluyor..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python main.py "$@"
