"""Local assistant contracts with a real loopback HTTP server, without model weights."""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtNetwork import QNetworkProxy  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slipsurface.analysis import AnalysisResults  # noqa: E402
from slipsurface.local_ai import (  # noqa: E402
    MAX_INPUT_BYTES,
    check_local_model,
    local_model_names,
    make_messages,
    project_context,
)
from slipsurface.project import acads_1a_project, empty_project  # noqa: E402
from slipsurface.ui.ollama import OllamaClient  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, condition, timeout=5):
    until = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() > until:
            raise AssertionError("Timed out waiting for local assistant")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def server():
    class State:
        requests = []
        mode = "ok"
        release = threading.Event()
        show = {"model_info": {"general.architecture": "test"}, "capabilities": ["completion"]}

    state = State()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def handle_request(self):
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size)) if size else None
            state.requests.append((self.path, body))
            if state.mode == "timeout":
                state.release.wait(3)
            if state.mode == "redirect":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/leak")
                self.end_headers()
                return
            if state.mode == "http_error":
                self.send_error(500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            if self.path == "/api/tags":
                data = {
                    "models": [
                        {"name": "test-local"},
                        {"name": "test:cloud"},
                        {"name": "alias", "remote_host": "https://ollama.com"},
                    ]
                }
                raw = json.dumps(data).encode()
            elif self.path == "/api/show":
                raw = json.dumps(state.show).encode()
            else:
                raw = (
                    json.dumps(
                        {"message": {"content": "Şev açıklaması <img src='https://invalid'>"}},
                        ensure_ascii=False,
                    ).encode()
                    + b"\n"
                )
                if state.mode != "incomplete":
                    raw += json.dumps({"done": True, "done_reason": "stop"}).encode()
            if state.mode == "malformed":
                raw = b"{not-json}\n"
            if state.mode == "oversize":
                raw = b"x" * (2 * 1024 * 1024 + 1)
            try:
                # Deliberately split a UTF-8 character across packets.
                if self.path == "/api/chat":
                    split = raw.find("Ş".encode()) + 1
                    self.wfile.write(raw[:split])
                    self.wfile.flush()
                    if state.mode == "cancel":
                        state.release.wait(3)
                    self.wfile.write(raw[split:])
                else:
                    self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=http.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    yield state, http.server_port
    state.release.set()
    http.shutdown()
    http.server_close()
    thread.join(timeout=2)


def test_context_uses_actual_results_and_excludes_stale_private_data():
    from slipsurface.geometry import CircularSurface
    from slipsurface.lem import analyze
    from slipsurface.optimizer import SearchResult

    project = acads_1a_project()
    project.summary.title = "PRIVATE-TITLE"
    project.summary.author = "PRIVATE-AUTHOR"
    project.annotations = [{"text": "PRIVATE-NOTE"}]
    before = project.to_dict()
    geom = project.build_geometry()
    surface = CircularSurface(20, 28, 28)
    lem, slices = analyze(geom, surface, project.build_materials())
    results = AnalysisResults(
        project.copy(),
        geom,
        results={"bishop": SearchResult(surface, lem.fos, lem, slices, 1)},
        errors={"spencer": "No convergence"},
    )
    text = project_context(project, results)
    assert "PRIVATE-" not in text
    data = json.loads(text)
    assert data["results"]["methods"][0]["factor_of_safety"] == lem.fos
    assert data["results"]["methods"][0]["converged"] == lem.converged
    assert data["results"]["errors"] == results.errors
    assert project.to_dict() == before
    project.materials[0].c += 1
    data = json.loads(project_context(project, results))
    assert data["results"] == {"status": "stale_excluded"}


def test_context_validation_and_nonfinite_inputs():
    p = empty_project()
    data = json.loads(project_context(p, geometry_error="No outer boundary"))
    assert data["validation"]
    assert data["results"]["status"] == "not_available"
    p = acads_1a_project()
    p.materials[0].c = float("nan")
    with pytest.raises(ValueError, match="geçersiz"):
        project_context(p)


def test_prompt_boundaries_preserve_current_input_and_drop_whole_history_pairs():
    history = [
        {"role": role, "content": "old" * 2000}
        for role in ("user", "assistant", "user", "assistant")
    ]
    messages = make_messages("Explain this", "en", history=history)
    assert messages[-1] == {"role": "user", "content": "Explain this"}
    assert len(messages) == 2
    assert "English" in messages[0]["content"]
    assert "Turkish" in make_messages("Açıkla", "tr")[0]["content"]
    with pytest.raises(ValueError, match="çok büyük"):
        make_messages("Explain", "en", "x" * MAX_INPUT_BYTES)
    for bad in (" ", "x" * 2001):
        with pytest.raises(ValueError):
            make_messages(bad, "tr")


@pytest.mark.parametrize(
    "metadata",
    [
        {"remote_host": "https://ollama.com", "model_info": {"a": 1}},
        {"remote_model": "hidden-alias", "model_info": {"a": 1}},
        {"model_info": {}},
        {"model_info": {"a": 1}, "capabilities": ["embedding"]},
    ],
)
def test_cloud_alias_and_unverifiable_models_are_rejected(metadata):
    with pytest.raises(ValueError):
        check_local_model(metadata)


def test_bad_model_list():
    with pytest.raises(ValueError):
        local_model_names({"models": "invalid"})


def test_real_http_streaming_and_metadata_preflight(app, server):
    state, port = server
    client = OllamaClient()
    assert client.manager.proxy().type() == QNetworkProxy.NoProxy
    models, chunks, answers, errors = [], [], [], []
    client.models_ready.connect(models.append)
    client.chunk.connect(chunks.append)
    client.completed.connect(lambda text, limited: answers.append((text, limited)))
    client.failed.connect(errors.append)
    client.list_models(port)
    wait_for(app, lambda: not client.busy)
    assert models == [["test-local"]]
    messages = make_messages("Help", "en")
    client.chat(port, "test-local", messages)
    wait_for(app, lambda: not client.busy)
    assert not errors
    assert answers == [("".join(chunks), False)]
    assert "Şev" in answers[0][0]
    assert [path for path, _ in state.requests] == ["/api/tags", "/api/show", "/api/chat"]
    body = state.requests[-1][1]
    assert body["messages"] == messages and body["stream"] is True
    assert "tools" not in body
    client.cancel(silent=True)
    assert not client._answer and client._pending is None


def test_remote_alias_never_receives_prompt(app, server):
    state, port = server
    state.show["remote_host"] = "https://ollama.com"
    client = OllamaClient()
    errors = []
    client.failed.connect(errors.append)
    client.chat(port, "innocent-alias", make_messages("private project", "en"))
    wait_for(app, lambda: not client.busy)
    assert errors and "Bulut" in errors[0]
    assert state.requests == [("/api/show", {"model": "innocent-alias"})]


@pytest.mark.parametrize("mode", ["redirect", "http_error", "malformed", "oversize", "incomplete"])
def test_protocol_failures_are_not_successful_answers(app, server, mode):
    state, port = server
    client = OllamaClient()
    errors, answers = [], []
    client.failed.connect(errors.append)
    client.completed.connect(lambda *args: answers.append(args))
    state.mode = mode
    if mode == "incomplete":
        client.chat(port, "test-local", make_messages("Hi", "en"))
    else:
        client.list_models(port)
    wait_for(app, lambda: not client.busy)
    assert errors and not answers
    assert all(path != "/leak" for path, _ in state.requests)


def test_timeout_and_cancellation_allow_reconnect(app, server):
    state, port = server
    client = OllamaClient()
    errors, answers = [], []
    client.failed.connect(errors.append)
    client.completed.connect(lambda *args: answers.append(args))
    client.timeout_ms = 30
    state.mode = "timeout"
    client.list_models(port)
    wait_for(app, lambda: not client.busy)
    assert "zaman aşımı" in errors[-1]
    state.release.set()
    state.mode = "cancel"
    state.release.clear()
    client.timeout_ms = 5000
    client.chat(port, "test-local", make_messages("Hi", "en"))
    wait_for(app, lambda: any(path == "/api/chat" for path, _ in state.requests))
    client.cancel()
    assert not client.busy and not answers and client._pending is None
    state.release.set()
    state.mode = "ok"
    client.chat(port, "test-local", make_messages("Again", "en"))
    wait_for(app, lambda: not client.busy)
    assert len(answers) == 1


def test_panel_read_only_default_and_project_change_cancel(app, server, monkeypatch, tmp_path):
    from slipsurface.ui.modeler import ModelerWindow

    prefs = QSettings(str(tmp_path / "preferences.ini"), QSettings.IniFormat)
    monkeypatch.setattr("slipsurface.ui.assistant.settings", lambda: prefs)
    state, port = server
    win = ModelerWindow(acads_1a_project())
    panel = win.assistant
    try:
        assert not win.assistant_dock.isVisible() and not panel.share.isChecked()
        assert panel.status.textFormat() == Qt.PlainText
        assert not state.requests
        panel.port.setValue(port)
        panel.refresh_models()
        wait_for(app, lambda: not panel.client.busy)
        before = win.doc.project.to_dict()
        panel.question.setText("Help")
        panel.send_question()
        wait_for(app, lambda: not panel.client.busy)
        body = state.requests[-1][1]
        assert "Current project snapshot" not in body["messages"][0]["content"]
        assert win.doc.project.to_dict() == before
        assert len(panel.history) == 2
        assert "<img" in panel.transcript.toPlainText()
        panel.share.setChecked(True)
        assert not panel.history
        state.mode = "cancel"
        panel.question.setText("Explain project")
        panel.send_question()
        wait_for(app, lambda: len([p for p, _ in state.requests if p == "/api/chat"]) == 2)
        win.doc.edit("change", lambda p: setattr(p.materials[0], "c", 10))
        assert not panel.client.busy and not panel.history
        assert not panel.transcript.toPlainText()
        assert not panel._scope
    finally:
        state.release.set()
        win.doc.mark_clean()
        win.close()
        app.processEvents()
