#!/usr/bin/env bash
# SlipSurfaceIQ LE - Linux/macOS: creates/updates the virtual environment and starts the app.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
fi
# Reinstall packages if requirements.txt changed (new release)
if ! cmp -s requirements.txt .venv/requirements.stamp; then
    echo "Installing / updating required packages..."
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv/requirements.stamp
fi
.venv/bin/python -c "import slipsurface, os; print('SlipSurfaceIQ LE', slipsurface.__version__, '-', os.path.dirname(slipsurface.__file__))"
exec .venv/bin/python main.py "$@"
