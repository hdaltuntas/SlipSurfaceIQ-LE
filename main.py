"""SlipSurfaceIQ LE — start the desktop application.

Run from an IDE (open this file and press Run) or from a terminal:

    python main.py                                  # modeler sized to the screen, empty project
    python main.py examples/anchored_cut.slp.json   # open a project file
    python main.py --example "ACADS EX1(a)"         # open a bundled example
    python main.py --list-examples
    python main.py --check                          # dependency check, no window

Works from any working directory: the project folder is put on sys.path.
The only application entry point is this file; install dependencies with
``python -m pip install -r requirements.txt`` before running it.
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

REQUIRED = {
    "PySide6": "PySide6",
    "numpy": "numpy",
    "scipy": "scipy",
    "shapely": "shapely",
    "reportlab": "reportlab",
    "ezdxf": "ezdxf",
    "qtawesome": "QtAwesome",
}
MIN_PYTHON = (3, 10)


def check_environment(verbose: bool = True) -> bool:
    """Verify Python version and required packages; print a readable report."""
    ok = True
    if sys.version_info < MIN_PYTHON:
        print(
            f"[ERROR] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required "
            f"(found {sys.version.split()[0]})."
        )
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
        print("[ERROR] Missing package(s): " + ", ".join(missing))
        print(
            f"        Install:  {Path(sys.executable).name} -m pip install -r "
            f"{ROOT / 'requirements.txt'}"
        )
    if ok and verbose:
        print(f"  Python     {sys.version.split()[0]}  ({sys.executable})")
        print("Environment ready.")
    return ok


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="SlipSurfaceIQ LE", description="2D limit equilibrium slope stability analysis"
    )
    p.add_argument("project", nargs="?", help="project file to open (.slp.json)")
    p.add_argument("--example", help="open a bundled example (name, see --list-examples)")
    p.add_argument("--list-examples", action="store_true", help="list the bundled examples")
    p.add_argument("--check", action="store_true", help="check the dependencies and exit")
    p.add_argument(
        "--smoke",
        type=float,
        metavar="SEC",
        help="open the window and close it after SEC seconds (automated test)",
    )
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

    if args.example and args.project:
        print("[ERROR] --example and a project file cannot be given together.")
        return 1
    if args.example and args.example not in EXAMPLES:
        print(f"[ERROR] Example not found: {args.example!r}. Options: {', '.join(EXAMPLES)}")
        return 1
    project_path = None
    if args.project:
        path = Path(args.project)
        if not path.is_absolute() and not path.exists():
            path = ROOT / path  # relative to the project folder
        if not path.exists():
            print(f"[ERROR] File not found: {args.project}")
            return 1
        project_path = str(path)
    return run(project_path=project_path, example=args.example, smoke=args.smoke)


if __name__ == "__main__":
    sys.exit(main())
