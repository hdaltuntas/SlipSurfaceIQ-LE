"""English UI catalogue; model identifiers and user input are never translated."""

from slipsurface.ui.preferences import settings
from PySide6.QtCore import QObject, QEvent
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QAbstractButton,
    QGroupBox,
    QComboBox,
    QTabWidget,
    QTableWidget,
    QToolBar,
    QDockWidget,
    QTreeWidget,
    QTreeWidgetItemIterator,
    QStatusBar,
    QLineEdit,
)

_language = "tr"
_filter = None


def initialize():
    global _language, _filter
    _language = settings().value("language", "tr")
    if _filter is None and QApplication.instance():
        _filter = _LanguageFilter(QApplication.instance())
        QApplication.instance().installEventFilter(_filter)


def tr(text):
    if not isinstance(text, str) or not text:
        return text
    source = REVERSE.get(text, text)
    return _english(source) if _language == "en" else source


def trf(template, *args):
    """Translate a template with positional {} fields, then format it."""
    return tr(template).format(*args)


def language():
    return _language


def _english(source):
    """English text for a Turkish source string (see slipsurface.textcat)."""
    return _CATALOG.translate(source)


def set_language(language):
    global _language
    if language not in ("tr", "en"):
        raise ValueError("Unsupported language")
    _language = language
    settings().setValue("language", language)
    app = QApplication.instance()
    if app:
        for window in app.topLevelWidgets():
            translate_window(window)


def translate_window(window):
    """Update captions in place; never recreate documents or change editable user data."""
    widgets = [window, *window.findChildren(QWidget)]
    protected = set()
    doc = getattr(window, "doc", None)
    if doc:
        p = doc.project
        protected.update(p.material_names())
        protected.update(t.name for t in p.support_types)
        protected.update(t.name for t in p.facing_types)
        protected.add(p.name)

    def caption(text):
        if text.startswith("▾  "):
            return "▾  " + tr(text[3:])
        return text if text in protected else tr(text)

    for action in window.findChildren(QAction):
        action.setText(caption(action.text()))
        action.setToolTip(caption(action.toolTip()))
        action.setStatusTip(caption(action.statusTip()))
    for widget in widgets:
        widget.setToolTip(caption(widget.toolTip()))
        widget.setStatusTip(caption(widget.statusTip()))
        if isinstance(widget, QStatusBar) and widget.currentMessage():
            widget.showMessage(caption(widget.currentMessage()))
        if isinstance(widget, QLineEdit):
            widget.setPlaceholderText(caption(widget.placeholderText()))
        if widget.isWindow():
            widget.setWindowTitle(caption(widget.windowTitle()))
        if isinstance(widget, (QLabel, QAbstractButton)):
            widget.setText(caption(widget.text()))
        if isinstance(widget, (QGroupBox, QToolBar, QDockWidget)):
            if isinstance(widget, QGroupBox):
                widget.setTitle(caption(widget.title()))
            else:
                widget.setWindowTitle(caption(widget.windowTitle()))
        if isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                widget.setTabText(index, caption(widget.tabText(index)))
        if isinstance(widget, QComboBox) and not widget.isEditable():
            blocked = widget.blockSignals(True)
            for index in range(widget.count()):
                widget.setItemText(index, caption(widget.itemText(index)))
            widget.blockSignals(blocked)
        if isinstance(widget, QTableWidget):
            blocked = widget.blockSignals(True)
            for column in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(column)
                if item:
                    item.setText(caption(item.text()))
            # Property names only. Editable cell values belong to the user.
            from PySide6.QtCore import Qt

            for row in range(widget.rowCount()):
                for column in range(widget.columnCount()):
                    item = widget.item(row, column)
                    if item and not item.flags() & Qt.ItemIsEditable:
                        item.setText(caption(item.text()))
            widget.blockSignals(blocked)
        if isinstance(widget, QTreeWidget):
            blocked = widget.blockSignals(True)
            iterator = QTreeWidgetItemIterator(widget)
            while iterator.value():
                item = iterator.value()
                for column in range(widget.columnCount()):
                    item.setText(column, caption(item.text(column)))
                iterator += 1
            widget.blockSignals(blocked)
        if hasattr(widget, "_last_refresh"):
            widget.refresh(*widget._last_refresh)
        if hasattr(widget, "steps"):
            widget.steps = [tr(step) for step in widget.steps]
            widget.updateGeometry()
        widget.update()


class _LanguageFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            translate_window(obj)
        return False


EN = {
    "&Dosya": "&File",
    "Dü&zen": "&Edit",
    "&Görünüm": "&View",
    "&Analiz": "&Analysis",
    "&Sınırlar": "&Boundaries",
    "&Yükleme": "&Loading",
    "&Destek": "&Support",
    "&Yüzeyler": "&Surfaces",
    "&Özellikler": "&Properties",
    "&Araçlar": "&Tools",
    "&Yardım": "&Help",
    "&Yeni": "&New",
    "&Aç…": "&Open…",
    "&Kaydet": "&Save",
    "&Farklı Kaydet…": "Save &As…",
    "Çı&kış": "E&xit",
    "Örnekler": "Examples",
    "Çizimi Dışa Aktar…": "Export Drawing…",
    "DXF İçe Aktar…": "Import DXF…",
    "DXF Dışa Aktar…": "Export DXF…",
    "Geri al": "Undo",
    "Yinele": "Redo",
    "Seçileni Sil": "Delete Selected",
    "Tümünü Göster": "Zoom Extents",
    "Tümünü göster (F2)": "Zoom Extents (F2)",
    "Yakınlaştır": "Zoom In",
    "Uzaklaştır": "Zoom Out",
    "Izgara ve Yakalama Ayarları…": "Grid and Snap Settings…",
    "Proje Ayarları…": "Project Settings…",
    "Proje Özeti…": "Project Summary…",
    "Hesapla": "Compute",
    "Yorumla": "Interpret",
    "PDF Rapor…": "PDF Report…",
    "Malzeme Tanımla…": "Define Materials…",
    "Yüzey Seçenekleri…": "Surface Options…",
    "Kayma Sınırlarını Sıfırla": "Reset Slip Limits",
    "Koordinatları Düzenle…": "Edit Coordinates…",
    "Seç": "Select",
    "Pencereyle Zoom": "Zoom Window",
    "Kaydır": "Pan",
    "Ölç": "Measure",
    "Dış Sınır Ekle": "Add External Boundary",
    "Malzeme Sınırı Ekle": "Add Material Boundary",
    "Su Tablosu Ekle": "Add Water Table",
    "Gerilme Çatlağı Ekle": "Add Tension Crack",
    "Derinlikten Gerilme Çatlağı…": "Tension Crack from Depth…",
    "Köşe Ekle": "Add Vertex",
    "Köşe Sil": "Delete Vertex",
    "Özellik Ata": "Assign Material",
    "Kayma Sınırları": "Slip Limits",
    "Kullanıcı Yüzeyi Çiz": "Draw User Surface",
    "Yayılı Yük Ekle": "Add Distributed Load",
    "Tekil Yük Ekle": "Add Line Load",
    "Destek Ekle": "Add Support",
    "Sismik Yük…": "Seismic Load…",
    "Destek Özelliklerini Tanımla…": "Define Support Properties…",
    "Tekil Bulon/Ankraj": "Single Bolt/Anchor",
    "Bulon Paterni": "Bolt Pattern",
    "Kaplama Tiplerini Tanımla…": "Define Facing Types…",
    "Kaplama Ata": "Assign Facing",
    "Kaplamayı Şev Yüzüne Ata": "Assign Facing to Slope",
    "Yok": "None",
    "Malzeme adı": "Material Name",
    "Ad + parametreler": "Name + Parameters",
    "Malzeme Etiketleri": "Material Labels",
    "Belge Görüntüleyici / Görüntü Seçenekleri": "Document Viewer / Display Options",
    "Hakkında": "About",
    "Geometri": "Geometry",
    "Destek": "Support",
    "Yükleme": "Loading",
    "Özellikler": "Properties",
    "Yüzeyler": "Surfaces",
    "Proje": "Project",
    "Tamam": "OK",
    "İptal": "Cancel",
    "Kapat": "Close",
    "Uygula": "Apply",
    "Evet": "Yes",
    "Hayır": "No",
    "Malzeme Özelliklerini Tanımla": "Define Material Properties",
    "Malzeme ekle": "Add Material",
    "Seçili malzemeyi sil": "Delete Selected Material",
    "Yukarı taşı": "Move Up",
    "Aşağı taşı": "Move Down",
    "Kopyala": "Copy",
    "Ad:": "Name:",
    "Dolgu:": "Fill:",
    "Birim hacim ağırlık (kN/m³):": "Unit Weight (kN/m³):",
    "Doygun birim hacim ağırlık (kN/m³):": "Saturated Unit Weight (kN/m³):",
    "Göçme kriteri:": "Failure Criterion:",
    "Genelleştirilmiş Hoek-Brown": "Generalized Hoek-Brown",
    "Özellik": "Property",
    "Değer": "Value",
    "Su tablosu bu malzemeye etki eder": "Apply Water Table to This Material",
    "Hu (piyezometrik yükseklik katsayısı):": "Hu (Piezometric Head Factor):",
    "Dayanım": "Strength",
    "Su Parametreleri": "Water Parameters",
    "Kohezyon c (kPa)": "Cohesion c (kPa)",
    "İçsel sürtünme açısı φ (°)": "Friction Angle φ (°)",
    "Tek eksenli basınç dayanımı σci (kPa)": "Intact UCS σci (kPa)",
    "Örselenme faktörü D": "Disturbance Factor D",
    "Dolgu rengi": "Fill Color",
    "Proje Ayarları": "Project Settings",
    "Genel": "General",
    "Yöntemler": "Methods",
    "Yeraltı Suyu": "Groundwater",
    "Sismik": "Seismic",
    "Gelişmiş": "Advanced",
    "Proje Özeti": "Project Summary",
    "Yüzey Seçenekleri": "Surface Options",
    "Koordinatlar": "Coordinates",
    "Izgara Ayarları": "Grid Settings",
    "Malzemeler": "Materials",
    "Sınırlar": "Boundaries",
    "Yükler": "Loads",
    "Destekler": "Supports",
    "Görüntü Seçenekleri": "Display Options",
    "Görüntü Seçenekleri…": "Display Options…",
    "Bu Malzemeyi Düzenle…": "Edit This Material…",
    "Belge Görüntüleyici": "Document Viewer",
    "Dış sınır": "External Boundary",
    "Malzeme sınırı": "Material Boundary",
    "Su tablası": "Water Table",
    "Gerilme çatlağı": "Tension Crack",
    "Kullanıcı yüzeyi": "User Surface",
    "Yazı": "Text",
    "Çizgi": "Line",
    "Ok": "Arrow",
    "Dikdörtgen": "Rectangle",
    "Elips": "Ellipse",
    "Notlar": "Annotations",
    "Renk": "Color",
    "Kalınlık": "Width",
    "Kaydet": "Save",
    "Aç": "Open",
    "Sil": "Delete",
    "Ekle": "Add",
    "Sıfırla": "Reset",
    "Varsayılan": "Default",
    "Hata": "Error",
    "Uyarı": "Warning",
    "Bilgi": "Information",
    "Sonuçlar": "Results",
    "Bilgi Görüntüleyici": "Information Viewer",
    "Global Minimum": "Global Minimum",
    "Malzeme": "Material",
    "Yöntem": "Method",
    "Dilimler": "Slices",
    "Güvenlik Sayısı": "Factor of Safety",
    "Başlık:": "Title:",
    "Hazırlayan:": "Author:",
    "Firma:": "Company:",
    "Açıklama:": "Description:",
    "Analiz:": "Analysis:",
    "Tarih:": "Date:",
    "Göçme yönü:": "Failure Direction:",
    "Sağdan sola": "Right to Left",
    "Soldan sağa": "Left to Right",
    "Dairesel": "Circular",
    "Dairesel olmayan": "Noncircular",
    "Kullanıcı tanımlı": "User Defined",
    "Hızlı": "Fast",
    "Normal": "Normal",
    "Hassas": "Fine",
    "Yatay": "Horizontal",
    "Düşey": "Vertical",
    "Aktif": "Active",
    "Pasif": "Passive",
    "Uzunluk (m):": "Length (m):",
    "Aralık (m):": "Spacing (m):",
    "Eğim (°):": "Angle (°):",
    "Kalın": "Bold",
    "Metin:": "Text:",
    "Boyut:": "Size:",
    "Renk:": "Color:",
    "Çizim": "Drawing",
    "Hesaplanıyor…": "Computing…",
    "Hesaplama": "Computation",
    "Yardım": "Help",
    "Araçlar": "Tools",
    "Kullanım": "Usage",
    "Yeni proje": "New Project",
    "Basit şev (10 m, 2H:1V)": "Simple Slope (10 m, 2H:1V)",
    "Katmanlı şev + YASS": "Layered Slope + Water Table",
    "Ankrajlı yarma + sürşarj": "Anchored Cut + Surcharge",
    "Gerilme çatlaklı şev": "Slope with Tension Crack",
    "Zemin çivisi + püskürtme beton": "Soil Nails + Shotcrete",
    "Yü&kleme": "&Loading",
    "Ö&zellikler": "&Properties",
    "Not Ekle (Yazı / Şekil)": "Add Annotation (Text / Shape)",
    "Kısayollar": "Keyboard Shortcuts",
    "İş akışı": "Workflow",
    "Ana araç çubuğu": "Main Toolbar",
    "Kaydedilmemiş": "Unsaved",
    "Kaydedilmemiş değişiklikler": "Unsaved Changes",
    "Model değişti. Kaydetmeden devam edilsin mi?": "The model has changed. Continue without saving?",
    "Farklı kaydet": "Save As",
    "Hesaplama hatası": "Computation Error",
    "Model değişti; yeniden hesaplayın (F5).": "Model changed; recompute (F5).",
    "Sonuç notları": "Result Annotations",
    "Önce geçerli bir dış sınır çizin.": "Draw a valid external boundary first.",
    "Yeni proje: Sınırlar → Dış Sınır Ekle ile başlayın.": "New project: start with Boundaries → Add "
    "External Boundary.",
    "Proje aç": "Open Project",
    "Açılamadı": "Could Not Open",
    "Model geçersiz.": "Invalid Model.",
    "Önce Hesapla (F5).": "Run Compute (F5) first.",
    "Hesaplama iptal ediliyor…": "Cancelling computation…",
    "Hesaplama durduruluyor; ardından pencere kapanacak…": "Stopping computation; the window will "
    "close afterwards…",
    "Çeşitli": "Miscellaneous",
    "Kaydedilmemiş dosya": "Unsaved File",
    "Renk seç": "Choose Color",
    "Varsayılanlara Dön": "Restore Defaults",
    "Dış sınır rengi": "External Boundary Color",
    "Malzeme sınırı rengi": "Material Boundary Color",
    "Sınır köşelerini göster": "Show Boundary Vertices",
    "Çizgi kalınlığı": "Line Width",
    "Cetveli göster": "Show Rulers",
    "Izgarayı göster": "Show Grid",
    "Kayma sınırları": "Slip Limits",
    "Bölge üzerinde": "On Region",
    "Etiket yazı boyutu": "Label Font Size",
    "FS lejantı (sağ alt)": "FS Legend (Bottom Right)",
    "Dilim sınırları ve dolgu": "Slice Boundaries and Fill",
    "Merkeze çizgiler": "Lines to Center",
    "FS yazısı": "FS Text",
    "Tüm yüzeyler (en düşük 25)": "All Surfaces (Lowest 25)",
    "Spline kontrol noktaları": "Spline Control Points",
    "Tüm Yüzeyler": "All Surfaces",
    "Bilgi Görüntüleyici…": "Information Viewer…",
    "Resmi Dışa Aktar…": "Export Image…",
    "FS Lejantı": "FS Legend",
    "Seçili Notu Sil": "Delete Selected Annotation",
    "Yardım için F1": "F1 for Help",
    "Izgara noktalarına yakala": "Snap to Grid Points",
    "Yatay/düşey kısıtla": "Constrain Horizontal/Vertical",
    "Nesne yakalama: uç, orta nokta, kesişim, en yakın": "Object Snap: Endpoint, Midpoint, "
    "Intersection, Nearest",
    "Yarım sinüs": "Half Sine",
    "Sabit (Spencer'e eşdeğer)": "Constant (Equivalent to Spencer)",
    "Kırpılmış sinüs": "Clipped Sine",
    "Varsayılanlar…": "Defaults…",
    "Ölçü birimleri": "Units",
    "Göçme yönü": "Failure Direction",
    "Veri çıktısı": "Data Output",
    "Maksimum (dilim tabloları raporda)": "Maximum (Slice Tables in Report)",
    "Düşey dilimler": "Vertical Slices",
    "Sarma düşey olmayan dilimler": "Sarma Nonvertical Slices",
    "Bu sürümde desteklenmiyor.": "Not supported in this version.",
    "Yakınsama seçenekleri": "Convergence Options",
    "Dilim sayısı:": "Number of Slices:",
    "Arayüz kuvvet fonksiyonu (GLE/Morgenstern-Price)": "Interslice Force Function "
    "(GLE/Morgenstern-Price)",
    "Başlangıç değeri:": "Start Value:",
    "Bitiş değeri:": "End Value:",
    "Boşluk suyu basıncı": "Pore Water Pressure",
    "Ru katsayısı": "Ru Coefficient",
    "Kuru (boşluk suyu yok)": "Dry (No Pore Water)",
    "Yöntem:": "Method:",
    "Suyun birim hacim ağırlığı γw:": "Water Unit Weight γw:",
    "Gerilme çatlağı suyu": "Tension Crack Water",
    "Kısmen dolu (%)": "Partially Filled (%)",
    "Çatlaktaki su:": "Crack Water:",
    "Psödo-statik sismik yük katsayıları": "Pseudo-static Seismic Coefficients",
    "Yatay katsayı kh:": "Horizontal Coefficient kh:",
    "Düşey katsayı kv:": "Vertical Coefficient kv:",
    "Çözüm kontrolleri": "Solution Checks",
    "mα < eşik ve negatif taban kayma direnci olan yüzeyleri reddet": "Reject surfaces with mα below "
    "threshold or negative base "
    "shear resistance",
    "mα eşik değeri (varsayılan 0.2):": "mα Threshold (Default 0.2):",
    "Maksimum arayüz kuvveti oranı (E/W):": "Maximum Interslice Force Ratio (E/W):",
    "Minimum kayma derinliği:": "Minimum Slip Depth:",
    "⚠ En az bir yöntem seçin.": "Select at least one method.",
    "Otomatik iyileştirmeli arama (Diferansiyel Evrim + Nelder-Mead)": "Automatic Refinement "
    "(Differential Evolution + "
    "Nelder-Mead)",
    "Yol araması + optimizasyon (DE + Nelder-Mead)": "Path Search + Optimization (DE + Nelder-Mead)",
    "— (kullanıcı tanımlı yüzey analiz edilir)": "— (Analyze User Defined Surface)",
    "▾  Seçenekler": "▾  Options",
    "Arama seçenekleri": "Search Options",
    "Poligonal — doğru parçaları (Slide2)": "Polygonal — Straight Segments",
    "Yumuşak eğri (B-spline)": "Smooth Curve (B-spline)",
    "Yalnızca konveks yüzeyler": "Convex Surfaces Only",
    "Arama yoğunluğu:": "Search Effort:",
    "Dairesel olmayan yüzey biçimi:": "Noncircular Surface Shape:",
    "Ara köşe / kontrol noktası sayısı:": "Intermediate Vertices / Control Points:",
    "Yüzey tipi seçenekleri": "Surface Type Options",
    "Kompozit yüzeyler": "Composite Surfaces",
    "Otomatik durum üretimi": "Automatic Case Generation",
    "Zayıf tabaka işleme:": "Weak Layer Handling:",
    "Kayma sınırları (slope limits)": "Slip Limits",
    "Kayma sınırlarını kullan": "Use Slip Limits",
    "Yüzey tipi:": "Surface Type:",
    "Önce Yüzeyler → Kullanıcı Yüzeyi Çiz ile bir yüzey çizin.": "First draw a surface using Surfaces "
    "→ Draw User Surface.",
    "Arama yöntemi:": "Search Method:",
    "Sol uç aralığı x:": "Left Endpoint Range x:",
    "Sağ uç aralığı x:": "Right Endpoint Range x:",
    "Yayılı Yük": "Distributed Load",
    "Üniform (q1 = q2)": "Uniform (q1 = q2)",
    "Doğrusal değişen (üçgen / trapez)": "Linearly Varying (Triangle / Trapezoid)",
    "Düşey (q, yatay metre başına)": "Vertical (q per Horizontal Metre)",
    "Yüzeye dik (q, sınır uzunluğu başına)": "Normal to Surface (q per Boundary Length)",
    "Başlangıç x₁:": "Start x₁:",
    "Bitiş x₂:": "End x₂:",
    "Yön:": "Direction:",
    "Tekil (Çizgisel) Yük": "Point (Line) Load",
    "Büyüklük P:": "Magnitude P:",
    "Kuvvet açısı:": "Force Angle:",
    "Destek Özelliklerini Tanımla": "Define Support Properties",
    "Düzlem dışı aralık:": "Out-of-plane Spacing:",
    "Çekme kapasitesi:": "Tensile Capacity:",
    "Kök (yapışma) dayanımı:": "Bond Strength:",
    "Kök boyu:": "Bond Length:",
    "Sıyrılma dayanımı:": "Pullout Strength:",
    "Varsayılan boy (otomatik yerleşim):": "Default Length (Automatic Placement):",
    "Kuvvet uygulama yöntemi": "Force Application",
    "Aktif — kuvvet itici kuvveti azaltır (F'ye bölünmez)": "Active — Reduces Driving Force (Not "
    "Divided by F)",
    "Pasif — kuvvet direnç gibi mobilize olur (T / F)": "Passive — Mobilized Resistance (T / F)",
    "Desteğe paralel": "Parallel to Support",
    "Kayma yüzeyine teğet": "Tangent to Slip Surface",
    "Kuvvet doğrultusu:": "Force Direction:",
    "Baş A — x:": "Head A — x:",
    "Baş A — y:": "Head A — y:",
    "Uç B — x:": "End B — x:",
    "Uç B — y:": "End B — y:",
    "Derinlikten Gerilme Çatlağı": "Tension Crack from Depth",
    "Çatlak derinliği z:": "Crack Depth z:",
    "Çatlaktaki su (doluluk):": "Crack Water (Fill):",
    "Çekme dayanımı (kN/m):": "Tensile Strength (kN/m):",
    "Izgara ve Yakalama Ayarları": "Grid and Snap Settings",
    "Izgara / SNAP aralığı:": "Grid / SNAP Spacing:",
    "Satır ekle": "Add Row",
    "Satır sil": "Delete Row",
    "Kaydet…": "Save…",
    "Büyüklük": "Magnitude",
    "Proje başlığı": "Project Title",
    "Hazırlayan": "Author",
    "Oluşturulma tarihi": "Created On",
    "Panodan yapıştır (satır satır)": "Paste from Clipboard (Line by Line)",
    "Tüm senaryolarda aynı proje özeti": "Same Project Summary for All Scenarios",
    "Tür": "Type",
    "Açıklama": "Description",
    "Des&tek": "&Support",
    "Senaryo": "Scenario",
    "köşe": "vertices",
    "YASS": "Water Table",
    "Kaplamalar": "Facings",
    "YASS rengi": "Water Table Color",
    "Malzeme dolgusu": "Material Fill",
    "Lejant": "Legend",
    "Not: Malzeme özellikleri tüm projede ortaktır. Bir malzeme silinirse, ona atanmış bölgeler ilk malzemeye döner.": "Material "
    "properties "
    "are "
    "shared "
    "across "
    "the "
    "project. "
    "Deleting "
    "a "
    "material "
    "reassigns "
    "its "
    "regions "
    "to "
    "the "
    "first "
    "material.",
}

from slipsurface.ui.translations_en import EXTRA  # noqa: E402

EN.update(EXTRA)
REVERSE = {value: key for key, value in EN.items() if "{}" not in key}


from slipsurface.textcat import Catalog  # noqa: E402

_CATALOG = Catalog(EN)
