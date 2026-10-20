"""Pytest setup: headless Qt by default so the suite runs in any IDE/CI."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# PySide6 can crash while the interpreter finalizes after all tests passed
# ("Fatal Python error: none_dealloc", seen with Python 3.10 on Linux). Once
# pytest has printed its summary, leave with its exit status and skip the
# interpreter teardown.
_exit_status = None


def pytest_sessionfinish(session, exitstatus):
    global _exit_status
    _exit_status = int(exitstatus)


def pytest_unconfigure(config):
    if _exit_status is not None and "PySide6.QtWidgets" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_exit_status)
