"""CLI: python -m slipsurface.patch [--check] [--apply] [version].

Without arguments: shows whether a newer published release exists and how
many files a delta update would change (nothing is modified).
"""

from __future__ import annotations

import argparse
import sys

from slipsurface import __version__
from slipsurface.updates import UpdateCheckError, fetch_latest, is_newer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m slipsurface.patch",
        description="Delta (changed-files-only) update for SlipSurfaceIQ LE",
    )
    parser.add_argument("version", nargs="?", help="target version (default: latest release)")
    parser.add_argument("--check", action="store_true", help="only show the plan (default)")
    parser.add_argument("--apply", action="store_true", help="download and copy changed files")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from slipsurface.patch.core import apply_update, plan_against_local, plan_update

    try:
        if args.version:
            target = args.version.lstrip("v")
        else:
            latest = fetch_latest()
            if not is_newer(latest.version):
                print(f"Güncel sürümdesiniz: {__version__}")
                return 0
            target = latest.version
        print(f"Güncelleme planlanıyor: {__version__} → {target}")
        if args.apply:
            plan = plan_update(__version__, target)
            summary = apply_update(plan, target)
            print(summary)
            print("Tamamlandı. Uygulamayı yeniden başlatın.")
        else:
            plan = plan_against_local(target)
            print(plan.summary())
            for d in plan.changed[:20]:
                print(f"  ~ {d.relpath}")
            for d in plan.new[:20]:
                print(f"  + {d.relpath}")
            for d in plan.removed[:20]:
                print(f"  - {d.relpath}")
            more = plan.download_count - 20
            if more > 0:
                print(f"  … (+{more} dosya daha)")
            print("--apply ile güncelleyin.")
    except UpdateCheckError as exc:
        print(f"Hata: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
