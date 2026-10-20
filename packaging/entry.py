"""Frozen desktop entry point, with an install-time CI smoke check."""

import os
import sys
from pathlib import Path

# A Windows GUI executable has no console streams. Some dependencies print warnings.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from main import main  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from smoke import smoke_test

        smoke_test(Path(sys.argv[2]))
    else:
        raise SystemExit(main())
