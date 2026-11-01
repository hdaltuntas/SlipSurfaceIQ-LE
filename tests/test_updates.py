"""Update check: release parsing (no network) and the Help-menu flow."""

import io
import json
import os
import time
import urllib.error

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from slipsurface import __version__, updates  # noqa: E402
from slipsurface.updates import ReleaseInfo, UpdateCheckError  # noqa: E402


def _opener(payload=None, exc=None):
    def open_(request, timeout):
        assert request.full_url == updates.LATEST_API
        assert request.get_header("User-agent").startswith("SlipSurfaceIQ-LE/")
        if exc is not None:
            raise exc
        return io.BytesIO(json.dumps(payload).encode())

    return open_


def test_versions_compare_numerically():
    assert updates.parse_version("v2026.1.5") == (2026, 1, 5)
    assert updates.parse_version("2026.1.5") == (2026, 1, 5)
    assert updates.parse_version("2026.1.5-rc1") is None
    assert updates.is_newer("2026.1.10", "2026.1.9")
    assert updates.is_newer("v2027.0.0", "2026.9.9")
    assert not updates.is_newer("2026.1.5", "2026.1.5")
    assert not updates.is_newer("2026.1.4", "2026.1.5")
    assert not updates.is_newer("nightly", "2026.1.5")


def test_fetch_latest_parses_the_release():
    info = updates.fetch_latest(
        opener=_opener(
            {
                "tag_name": "v2026.2.0",
                "html_url": "https://github.com/hdaltuntas/SlipSurfaceIQ-LE/releases/tag/v2026.2.0",
                "body": "Notes",
                "published_at": "2026-11-02T10:00:00Z",
            }
        )
    )
    assert info == ReleaseInfo(
        "2026.2.0",
        "https://github.com/hdaltuntas/SlipSurfaceIQ-LE/releases/tag/v2026.2.0",
        "Notes",
        "2026-11-02",
    )


def test_fetch_latest_only_links_to_the_project_release_page():
    info = updates.fetch_latest(
        opener=_opener({"tag_name": "2026.2.0", "html_url": "https://example.com/x"})
    )
    assert info.url == updates.RELEASES_PAGE


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"exc": urllib.error.URLError("offline")}, "offline"),
        ({"exc": urllib.error.HTTPError(updates.LATEST_API, 404, "nf", {}, None)}, "no published"),
        ({"exc": urllib.error.HTTPError(updates.LATEST_API, 403, "rl", {}, None)}, "HTTP 403"),
        ({"exc": TimeoutError("timed out")}, "timed out"),
        ({"payload": ["not", "a", "release"]}, "invalid response"),
        ({"payload": {"tag_name": "latest"}}, "unrecognised release tag"),
    ],
)
def test_fetch_latest_reports_failures(kwargs, message):
    with pytest.raises(UpdateCheckError, match=message):
        updates.fetch_latest(opener=_opener(**kwargs))


def test_notes_excerpt_strips_headings_and_truncates():
    from slipsurface.ui.updates import notes_excerpt

    notes = "# Title\n\n## Section\n" + "\n".join(f"- item {i}" for i in range(20))
    text = notes_excerpt(notes, lines=4)
    assert text.splitlines() == ["Title", "Section", "- item 0", "- item 1", "…"]


def test_ssl_context_has_certificates():
    assert updates.ssl_context().cert_store_stats()["x509_ca"] > 0


# ---------------------------------------------------------------- UI
@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def prefs():
    from slipsurface.ui import updates as ui
    from slipsurface.ui.preferences import settings

    keys = (ui.AUTO_KEY, ui.LAST_KEY, ui.SKIP_KEY)
    saved = {k: settings().value(k) for k in keys}
    for k in keys:
        settings().remove(k)
    yield settings()
    for k, v in saved.items():
        if v is None:
            settings().remove(k)
        else:
            settings().setValue(k, v)


def _run(app, checker, manual):
    assert checker.check(manual)
    t0 = time.time()
    while checker.busy and time.time() - t0 < 10:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return checker.dialog


def _checker(app, result):
    from PySide6.QtWidgets import QWidget

    from slipsurface.ui.updates import UpdateChecker

    def fetch():
        if isinstance(result, Exception):
            raise result
        return result

    parent = QWidget()
    return parent, UpdateChecker(parent, fetch=fetch)


def test_manual_check_offers_a_newer_release_and_can_skip_it(app, prefs):
    from slipsurface.ui import updates as ui

    parent, checker = _checker(app, ReleaseInfo("2099.0.0", updates.RELEASES_PAGE, "Notes"))
    box = _run(app, checker, manual=True)
    assert box is not None and "2099.0.0" in box.text() and __version__ in box.text()
    assert box.informativeText() == "Notes" and not box.detailedText()
    labels = {b.text(): b for b in box.buttons()}
    skip = next(b for t, b in labels.items() if "Atla" in t or "Skip" in t)
    skip.click()
    app.processEvents()
    assert prefs.value(ui.SKIP_KEY) == "2099.0.0"
    assert prefs.value(ui.LAST_KEY, 0.0, type=float) > 0

    # automatic checks respect the skipped version; manual checks do not
    checker.dialog = None
    assert _run(app, checker, manual=False) is None
    assert _run(app, checker, manual=True) is not None


def test_manual_check_reports_up_to_date_and_errors(app, prefs):
    parent, checker = _checker(app, ReleaseInfo(__version__, updates.RELEASES_PAGE))
    box = _run(app, checker, manual=True)
    assert box.icon() == QMessageBox.Information and __version__ in box.text()

    parent, checker = _checker(app, UpdateCheckError("HTTP 403"))
    box = _run(app, checker, manual=True)
    assert box.icon() == QMessageBox.Warning and "HTTP 403" in box.text()


def test_automatic_check_is_silent_on_failure_and_daily(app, prefs):
    from slipsurface.ui import updates as ui

    parent, checker = _checker(app, UpdateCheckError("offline"))
    assert ui.auto_check_due()
    assert _run(app, checker, manual=False) is None

    prefs.setValue(ui.LAST_KEY, time.time())
    assert not ui.auto_check_due()
    assert not checker.check_if_due()
    assert ui.auto_check_due(now=time.time() + ui.AUTO_INTERVAL + 1)

    ui.set_auto_enabled(False)
    assert not ui.auto_check_due(now=time.time() + 10 * ui.AUTO_INTERVAL)


def test_help_menu_has_update_actions(app, prefs):
    from slipsurface.project import empty_project
    from slipsurface.ui.modeler import ModelerWindow
    from slipsurface.ui import updates as ui

    w = ModelerWindow(empty_project())
    try:
        texts = [a.text() for a in w.menuBar().actions()[-1].menu().actions()]
        assert any("Check for Updates" in t for t in texts)
        assert w.a_auto_updates.isChecked()
        w.a_auto_updates.setChecked(False)
        assert not ui.auto_enabled()
    finally:
        w.doc.mark_clean()
        w.close()
