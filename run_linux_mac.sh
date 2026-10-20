#!/usr/bin/env bash
# SlipSurface LE - Linux/macOS: sanal ortami kurar / gunceller ve programi baslatir.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Sanal ortam olusturuluyor..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
fi
# requirements.txt degistiyse (yeni surum) paketleri yeniden kur
if ! cmp -s requirements.txt .venv/requirements.stamp; then
    echo "Gerekli paketler kuruluyor / guncelleniyor..."
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv/requirements.stamp
fi
.venv/bin/python -c "import slipsurface, os; print('SlipSurface LE', slipsurface.__version__, '-', os.path.dirname(slipsurface.__file__))"
exec .venv/bin/python main.py "$@"
