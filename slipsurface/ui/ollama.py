"""Asynchronous, cancellable Ollama client restricted to IPv4 loopback.

No proxy, redirects, cloud fallback, API keys, model downloads or tool execution.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

from slipsurface.local_ai import check_local_model, local_model_names

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ANSWER_CHARS = 20_000


class OllamaClient(QObject):
    models_ready = Signal(list)
    chunk = Signal(str)
    completed = Signal(str, bool)  # answer, output token limit reached
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._fail("Ollama isteği zaman aşımına uğradı."))
        self._reply = None
        self._pending = None
        self.timeout_ms = 300_000

    @property
    def busy(self):
        return self._reply is not None

    def list_models(self, port: int):
        self._begin(port)
        self._request("tags")

    def chat(self, port: int, model: str, messages: list[dict]):
        self._begin(port)
        if not model or "cloud" in model.lower():
            raise ValueError("Bilgisayarınıza indirilmiş bir model seçin.")
        self._pending = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": 16384, "num_predict": 1024, "temperature": 0.2},
            "keep_alive": "5m",
        }
        self._request("show", {"model": model})

    def _begin(self, port):
        if self.busy:
            raise ValueError("Önce devam eden isteği durdurun.")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Ollama portu 1–65535 arasında olmalı.")
        self._port = port

    def _request(self, operation, body=None):
        self._operation = operation
        self._buffer = b""
        self._received = 0
        self._answer = ""
        self._done = False
        self._limited = False
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self._port}/api/{operation}"))
        request.setAttribute(
            QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy
        )
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        reply = (
            self.manager.get(request)
            if body is None
            else self.manager.post(request, json.dumps(body, ensure_ascii=False).encode("utf-8"))
        )
        self._reply = reply
        reply.readyRead.connect(lambda: self._read(reply))
        reply.finished.connect(lambda: self._finished(reply))
        self.timer.start(self.timeout_ms if operation == "chat" else min(self.timeout_ms, 10_000))
        self.busy_changed.emit(True)

    def _read(self, reply):
        if reply is not self._reply:
            return
        data = bytes(reply.readAll())
        self._received += len(data)
        if self._received > MAX_RESPONSE_BYTES:
            self._fail("Ollama yanıtı boyut sınırını aştı.")
            return
        self._buffer += data
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if self._operation != "chat" or status != 200:
            return
        try:
            while b"\n" in self._buffer:
                if reply is not self._reply:
                    return
                line, self._buffer = self._buffer.split(b"\n", 1)
                if line.strip():
                    self._event(self._decode(line))
        except (ValueError, TypeError) as exc:
            self._fail(str(exc))

    @staticmethod
    def _decode(data):
        try:
            obj = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Ollama yanıtı okunamadı.") from exc
        if not isinstance(obj, dict):
            raise ValueError("Ollama yanıtı okunamadı.")
        if obj.get("error"):
            raise ValueError("Ollama hatası: " + str(obj["error"])[:500])
        return obj

    def _event(self, event):
        if self._done:
            raise ValueError("Ollama tamamlanmış yanıtın ardından veri gönderdi.")
        if event.get("remote_host") or event.get("remote_model"):
            raise ValueError("Bulut modeli yanıtı reddedildi.")
        message = event.get("message", {})
        if not isinstance(message, dict) or message.get("tool_calls"):
            raise ValueError("Asistan yalnızca metin yanıtlarını destekler.")
        text = message.get("content", "")
        if not isinstance(text, str):
            raise ValueError("Ollama yanıtı okunamadı.")
        if len(self._answer) + len(text) > MAX_ANSWER_CHARS:
            raise ValueError("Ollama yanıtı boyut sınırını aştı.")
        if text:
            self._answer += text
            self.chunk.emit(text)
        if event.get("done") is True:
            self._done = True
            self._limited = event.get("done_reason") == "length"

    def _finished(self, reply):
        if reply is not self._reply:
            return
        self._read(reply)
        if reply is not self._reply:
            return
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        error = reply.error()
        operation, data = self._operation, self._buffer
        self._dispose()
        try:
            if status is not None and status != 200:
                raise ValueError(
                    f"Ollama HTTP hatası: {status}. Modeli ve bağlantıyı kontrol edin."
                )
            if error != QNetworkReply.NoError:
                raise ValueError(
                    "Ollama bağlantısı kurulamadı veya kesildi. Ollama'nın çalıştığını kontrol edin."
                )
            if operation == "tags":
                self.models_ready.emit(local_model_names(self._decode(data)))
            elif operation == "show":
                info = self._decode(data)
                check_local_model(info)
                payload, self._pending = self._pending, None
                if "thinking" in info.get("capabilities", []):
                    payload["think"] = False
                self._request("chat", payload)
                return
            else:
                if data.strip():
                    self._event(self._decode(data))
                if not self._done or not self._answer.strip():
                    raise ValueError("Yanıt tamamlanmadı. Eksik yanıt konuşma geçmişine eklenmedi.")
                self.completed.emit(self._answer, self._limited)
        except (ValueError, TypeError) as exc:
            self.failed.emit(str(exc))
        self._pending = None
        self.busy_changed.emit(False)

    def _dispose(self):
        self.timer.stop()
        reply, self._reply = self._reply, None
        if reply is not None:
            if not reply.isFinished():
                reply.abort()
            reply.deleteLater()

    def _fail(self, message):
        self._dispose()
        self._pending = None
        self.failed.emit(message)
        self.busy_changed.emit(False)

    def cancel(self, silent=False):
        was_busy = self.busy
        if was_busy:
            self._dispose()
            if not silent:
                self.failed.emit("İstek durduruldu. Eksik yanıt konuşma geçmişine eklenmedi.")
            self.busy_changed.emit(False)
        self._pending = None
        self._buffer = b""
        self._answer = ""
