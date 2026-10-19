"""SlipSurface LE — start the desktop application.

Run from an IDE (PyCharm / VS Code / Spyder: open this file and press Run) or
from a terminal:

    python main.py                                  # Modeler with the default example
    python main.py examples/ankrajli_yarma.slp.json # open a project file
    python main.py --example "Katmanlı şev + YASS"  # open a bundled example
    python main.py --list-examples
    python main.py --check                          # dependency check, no window

Works from any working directory: the project folder is put on sys.path, so
no installation is required (``pip install -e .`` is optional).
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED = {"PySide6": "PySide6", "numpy": "numpy", "scipy": "scipy", "shapely": "shapely",
            "reportlab": "reportlab"}
MIN_PYTHON = (3, 10)


def check_environment(verbose: bool = True) -> bool:
    """Verify Python version and required packages; print a readable report."""
    ok = True
    if sys.version_info < MIN_PYTHON:
        print(f"[HATA] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ gerekli "
              f"(bulunan {sys.version.split()[0]}).")
        ok = False
    missing = []
    for mod, pip_name in REQUIRED.items():
        try:
            m = importlib.import_module(mod)
            if verbose:
                print(f"  {mod:10s} {getattr(m, '__version__', '?')}")
        except ImportError:
            missing.append(pip_name)
    if missing:
        ok = False
        print("[HATA] Eksik paket(ler): " + ", ".join(missing))
        print(f"       Kurulum:  {Path(sys.executable).name} -m pip install -r "
              f"{ROOT / 'requirements.txt'}")
    if ok and verbose:
        print(f"  Python     {sys.version.split()[0]}  ({sys.executable})")
        print("Ortam hazır.")
    return ok


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="SlipSurface LE",
                                description="2D limit denge şev stabilite programı")
    p.add_argument("project", nargs="?", help="açılacak proje dosyası (.slp.json)")
    p.add_argument("--example", help="paketteki bir örneği aç (adı, --list-examples)")
    p.add_argument("--list-examples", action="store_true", help="örnekleri listele")
    p.add_argument("--check", action="store_true", help="bağımlılıkları kontrol et ve çık")
    p.add_argument("--smoke", type=float, metavar="SN",
                   help="pencereyi açıp SN saniye sonra kapat (otomatik test)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.check:
        return 0 if check_environment() else 1
    if not check_environment(verbose=False):
        return 1

    from slipsurface.project import EXAMPLES
    if args.list_examples:
        for name in EXAMPLES:
            print(name)
        return 0

    # HiDPI: crisp rendering on scaled Windows displays
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    from slipsurface.ui.app import run
    project_path = None
    if args.project:
        path = Path(args.project)
        if not path.is_absolute() and not path.exists():
            path = ROOT / path                     # relative to the project folder
        if not path.exists():
            print(f"[HATA] Dosya bulunamadı: {args.project}")
            return 1
        project_path = str(path)
    if args.example and args.example not in EXAMPLES:
        print(f"[HATA] Örnek bulunamadı: {args.example!r}. Seçenekler: {', '.join(EXAMPLES)}")
        return 1
    if args.example and args.project:
        print("[HATA] --example ve bir proje dosyası aynı anda verilemez.")
        return 1
    return run(project_path=project_path, example=args.example, smoke=args.smoke)


if __name__ == "__main__":
    sys.exit(main())
