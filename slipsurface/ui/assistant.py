"""Optional local assistant panel. All answers are plain text and read-only."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from slipsurface.local_ai import make_messages, project_context
from slipsurface.ui.i18n import language, tr
from slipsurface.ui.ollama import OllamaClient
from slipsurface.ui.preferences import fit_to_screen, settings

SETUP_TR = """Yerel AI kurulumu

1. https://ollama.com/download adresinden işletim sisteminize uygun Ollama'yı kurun.
2. Ollama'nın bulut özelliklerini kapatın. Kullanıcı ortam değişkeni olarak
   OLLAMA_NO_CLOUD=1 ayarlayıp Ollama'yı yeniden başlatın. Alternatif olarak
   ~/.ollama/server.json dosyasına mevcut ayarları koruyarak
   "disable_ollama_cloud": true ekleyin.
3. Terminalde bir yerel model indirin. Başlangıç örneği:
   ollama pull qwen3:4b
4. Ollama çalışırken panelde 'Modelleri yenile' düğmesine basın ve model seçin.
   Linux'ta gerekirse Ollama hizmetini başlatın veya 'ollama serve' çalıştırın.
5. Sorunuzu yazıp Gönder'e basın. Modele özel yardım için proje paylaşımını seçin.

Model indirme internet gerektirir; indirilen yerel modelle sohbet çevrimdışı
çalışabilir. Model dosyaları kurulum paketine dahil değildir. qwen3:4b yaklaşık
2,5 GB indirilir; çalışma belleği ihtiyacı daha fazladır. Hız ve kalite model,
RAM ve GPU'ya bağlıdır. Bu örnek model bir mühendislik doğrulaması değildir.

Bağlantı yalnızca 127.0.0.1 üzerindedir; port varsayılan olarak 11434'tür.
Bulut modelleri ve yönlendirmeler reddedilir. API anahtarı veya abonelik yoktur.
Yerel Ollama yapılandırmasının kontrolü sizdedir; bulut özelliklerini kapatın.

Asistan proje değiştirmez, hesap çalıştırmaz veya Python kodu yürütmez.
Proje paylaşımı varsayılan olarak kapalıdır. Açarsanız geometri, malzemeler,
yükler, analiz ayarları ve güncel sonuç özeti aynı bilgisayardaki modele gider.
Başlık, hazırlayan, dosya yolu ve çizim notları gönderilmez. Gönderilecek proje
verisini 'Bağlamı göster' ile inceleyebilirsiniz. Sorunuzun metni her zaman gider.
Konuşmalar yalnızca bellekte tutulur; proje değiştiğinde veya pencere kapanınca
silinir. Geçmiş çok uzarsa eski mesaj çiftleri sonraki istekten çıkarılır.
Model çıktıları hatalı olabilir; hesap sonuçlarını ve yorumları gözden geçirin.

Bağlantı hatası: Ollama'nın çalıştığını ve portunu kontrol edin.
Model yok: Yukarıdaki model indirme komutunu çalıştırıp listeyi yenileyin.
Bellek hatası: Daha küçük bir yerel model seçin veya diğer uygulamaları kapatın.
Yanıt yavaş: Durdur ile isteği iptal edebilir, daha küçük bir model deneyebilirsiniz.
"""

SETUP_EN = """Local AI setup

1. Install Ollama for your OS from https://ollama.com/download.
2. Disable Ollama cloud features: set the user environment variable
   OLLAMA_NO_CLOUD=1 and restart Ollama. Alternatively, add
   "disable_ollama_cloud": true to ~/.ollama/server.json, keeping existing settings.
3. Download a local model in a terminal. A starting example:
   ollama pull qwen3:4b
4. With Ollama running, click 'Refresh models' in this panel and select a model.
   On Linux, start the Ollama service or run 'ollama serve' if needed.
5. Enter a question and click Send. Enable project sharing for model-specific help.

Downloading needs internet; chat with a downloaded local model can work offline.
Model weights are not bundled in the app installer. qwen3:4b is about a 2.5 GB
download and needs additional runtime memory. Speed and quality depend on model,
RAM and GPU. This example model has not been validated for engineering decisions.

Connections only go to 127.0.0.1, port 11434 by default. Cloud models and redirects
are rejected. No API key or subscription is needed. You control the local Ollama
configuration; disable its cloud features.

The assistant cannot edit projects, run calculations or execute Python.
Project sharing is off by default. When enabled, geometry, materials, loads,
analysis settings and current result summaries go to the model on this computer.
Title, author, file path and drawing notes are excluded. Use 'Preview context' to
inspect project data before sending. Your question text is always sent.
Conversations are in memory only and cleared on project changes or window close.
Older message pairs are omitted from later requests if history grows too large.
Model outputs can be wrong; review calculation results and explanations.

Connection error: Check that Ollama is running and the port is correct.
No models: Run the model download command above and refresh the list.
Out of memory: Select a smaller local model or close other applications.
Slow response: Click Stop to cancel and consider a smaller model.
"""


class AssistantPanel(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.client = OllamaClient(self)
        self.history = []
        self._question = ""
        self._scope = None
        self._context = ""
        layout = QVBoxLayout(self)
        intro = QLabel(tr("Aynı bilgisayardaki Ollama ile kullanım desteği ve sonuç açıklaması."))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        try:
            port = int(settings().value("local_ai/port", 11434))
        except (TypeError, ValueError):
            port = 11434
        self.port.setValue(port if 1 <= port <= 65535 else 11434)
        form.addRow(tr("Ollama portu (127.0.0.1):"), self.port)
        self.model = QComboBox()
        self.model.setMinimumContentsLength(15)
        self.model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        form.addRow(tr("Yerel model:"), self.model)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.refresh = QPushButton(tr("Modelleri yenile"))
        self.help = QPushButton(tr("Kurulum yardımı"))
        row.addWidget(self.refresh)
        row.addWidget(self.help)
        layout.addLayout(row)
        self.share = QCheckBox(tr("Proje ve güncel sonuçları yerel modelle paylaş"))
        layout.addWidget(self.share)
        self.preview = QPushButton(tr("Bağlamı göster"))
        layout.addWidget(self.preview)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setMaximumBlockCount(1000)
        self.transcript.setMinimumHeight(150)
        layout.addWidget(self.transcript, 1)
        self.question = QLineEdit()
        self.question.setMaxLength(2000)
        self.question.setPlaceholderText(tr("Sorunuzu yazın…"))
        layout.addWidget(self.question)
        row = QHBoxLayout()
        self.send = QPushButton(tr("Gönder"))
        self.stop = QPushButton(tr("Durdur"))
        self.clear = QPushButton(tr("Konuşmayı temizle"))
        for button in (self.send, self.stop, self.clear):
            row.addWidget(button)
        layout.addLayout(row)
        self.status = QLabel(tr("Ollama'yı başlatın ve modelleri yenileyin."))
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh.clicked.connect(self.refresh_models)
        self.help.clicked.connect(self.show_help)
        self.preview.clicked.connect(self.preview_context)
        self.send.clicked.connect(self.send_question)
        self.question.returnPressed.connect(self.send_question)
        self.stop.clicked.connect(lambda: self.client.cancel())
        self.clear.clicked.connect(self.reset_conversation)
        self.share.toggled.connect(lambda _: self.reset_conversation())
        self.port.valueChanged.connect(self._port_changed)
        self.model.currentIndexChanged.connect(lambda _: self.reset_conversation())
        self.client.models_ready.connect(self._models_ready)
        self.client.chunk.connect(self._append_chunk)
        self.client.completed.connect(self._completed)
        self.client.failed.connect(self._failed)
        self.client.busy_changed.connect(self._busy_changed)
        self._busy_changed(False)

    def _busy_changed(self, busy):
        for widget in (self.port, self.model, self.refresh, self.share):
            widget.setEnabled(not busy)
        self.send.setEnabled(not busy and self.model.currentData() is not None)
        self.stop.setEnabled(busy)
        self.question.setEnabled(not busy)

    def _port_changed(self, _):
        self.reset_conversation()
        self.model.clear()
        self._busy_changed(False)

    def refresh_models(self):
        if self.client.busy:
            return
        self.reset_conversation()
        self.model.clear()
        self.status.setText(tr("Yerel modeller aranıyor…"))
        self.client.list_models(self.port.value())

    def _models_ready(self, models):
        selected = settings().value("local_ai/model", "")
        self.model.blockSignals(True)
        self.model.clear()
        for name in models:
            self.model.addItem(name, name)
        index = self.model.findData(selected)
        if index >= 0:
            self.model.setCurrentIndex(index)
        self.model.blockSignals(False)
        self.status.setText(
            tr("Hazır. Yanıtları mühendislik değerlendirmesiyle kontrol edin.")
            if models
            else tr("Yerel model bulunamadı. Kurulum yardımını açın.")
        )

    def _current_context(self):
        if not self.share.isChecked():
            return ""
        return project_context(
            self.window.doc.project, self.window.last_results, self.window.doc.geometry_error
        )

    def send_question(self):
        if self.client.busy or self.model.currentData() is None:
            return
        question = self.question.text().strip()
        try:
            context = self._current_context()
            model = self.model.currentData()
            scope = (model, self.port.value(), language(), context)
            if self._scope is not None and scope != self._scope:
                self.reset_conversation()
            messages = make_messages(question, language(), context, self.history)
            self._scope = scope
            self._context = context
            self._question = question
            self.client.chat(self.port.value(), model, messages)
        except ValueError as exc:
            self._failed(str(exc))
            return
        settings().setValue("local_ai/port", self.port.value())
        settings().setValue("local_ai/model", model)
        self.transcript.appendPlainText(tr("Siz:") + " " + question)
        label = tr("Proje paylaşıldı") if context else tr("Genel yardım; proje paylaşılmadı")
        self.transcript.appendPlainText(f"[{model} · {label}]\n" + tr("Yerel asistan:") + "\n")
        self.question.clear()
        self.status.setText(tr("Yanıt hazırlanıyor; ilk yükleme zaman alabilir…"))

    def _append_chunk(self, text):
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def _completed(self, answer, limited):
        if limited:
            self._failed(
                "Yanıt uzunluk sınırına ulaştı; geçmişe eklenmedi. Daha dar bir soru sorun."
            )
            return
        self.history.extend(
            [{"role": "user", "content": self._question}, {"role": "assistant", "content": answer}]
        )
        self.history = self.history[-8:]
        self._question = ""
        self.status.setText(tr("Hazır. Yanıtları mühendislik değerlendirmesiyle kontrol edin."))

    def _failed(self, message):
        self.status.setText(tr(message))
        self.transcript.appendPlainText("\n[" + tr(message) + "]")
        self._question = ""

    def reset_conversation(self):
        self.client.cancel(silent=True)
        self.history.clear()
        self._question = ""
        self._scope = None
        self._context = ""
        self.transcript.clear()

    def context_changed(self):
        if self.history or self._question or self.transcript.toPlainText():
            self.reset_conversation()
            self.status.setText(tr("Proje veya sonuçlar değişti; konuşma temizlendi."))

    def _text_dialog(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(title))
        fit_to_screen(dialog, 900, 700)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def show_help(self):
        self._text_dialog("Kurulum yardımı", SETUP_TR if language() == "tr" else SETUP_EN)

    def preview_context(self):
        import json

        try:
            context = self._current_context()
            text = (
                json.dumps(json.loads(context), ensure_ascii=False, indent=2)
                if context
                else tr("Proje paylaşımı kapalı. Yalnızca sorunuz ve konuşma geçmişi gönderilir.")
            )
            self._text_dialog("Bağlamı göster", text)
        except ValueError as exc:
            self.status.setText(tr(str(exc)))
