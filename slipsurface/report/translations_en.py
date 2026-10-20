"""English catalogue of the PDF report (Turkish source -> English); see textcat."""

from slipsurface.textcat import Catalog

PDF_EN = {
    # page decoration
    "Şev Stabilite Analiz Raporu": "Slope Stability Analysis Report",
    "SLIPSURFACEIQ LE  ·  2B LİMİT DENGE ANALİZİ": "SLIPSURFACEIQ LE  ·  2D LIMIT EQUILIBRIUM ANALYSIS",
    "Rapor No": "Report No.",
    "SlipSurfaceIQ LE {} ile üretilmiştir.": "Produced with SlipSurfaceIQ LE {}.",
    "{} sayfa": "{} pages",
    "Hazırlayan": "Prepared by",
    "Sayfa": "Page",
    "Ek": "Appendix",
    "Tablo": "Table",
    "Şekil": "Figure",
    # cover
    "Yeterli": "Adequate",
    "Sınırda": "Marginal",
    "Yetersiz": "Inadequate",
    "Proje": "Project",
    "Analiz": "Analysis",
    "Kontrol eden": "Checked by",
    "Firma / kurum": "Company",
    "Rapor tarihi": "Report date",
    "Analiz zamanı": "Analysed at",
    "Model dosyası": "Model file",
    "kaydedilmemiş": "not saved",
    "Hedef FS": "Target FS",
    "Hedef FS tanımlanmadı": "No target FS defined",
    "KRİTİK GÜVENLİK SAYISI": "CRITICAL FACTOR OF SAFETY",
    "SONUÇ YOK": "NO RESULT",
    "Kritik kayma yüzeyi (global minimum)": "Critical slip surface (global minimum)",
    "<b>Açıklamalar</b>": "<b>Comments</b>",
    "İçindekiler": "Contents",
    # summary
    "Özet": "Summary",
    "poligonal": "polyline",
    "dairesel": "circular",
    "dairesel olmayan": "non-circular",
    "kullanıcı tanımlı": "user-defined",
    "Bu raporda <b>{}</b> şevinin 2B limit denge analizi sunulmaktadır. Analizde {} yöntem kullanılmış, kritik kayma yüzeyi {} yüzey araması ile belirlenmiştir.":
        "This report presents the 2D limit equilibrium analysis of the <b>{}</b> slope. {} "
        "method(s) were used and the critical slip surface was found by a {} surface search.",
    " En düşük güvenlik sayısı <b>{}</b> yöntemiyle <b>FS = {}</b> olarak bulunmuştur":
        " The lowest factor of safety, <b>FS = {1}</b>, was obtained with the <b>{0}</b> method",
    "üzerindedir": "above",
    "altındadır": "below",
    "; bu değer hedef güvenlik sayısı FS = {} değerinin {} (<font color='{}'><b>{}</b></font>).":
        "; this value is {1} the target factor of safety FS = {0} "
        "(<font color='{2}'><b>{3}</b></font>).",
    " Yöntemler arasında FS {} – {} aralığında değişmektedir (fark %{}).":
        " Across the methods FS ranges from {} to {} (difference {}%).",
    "{} dış yük": "{} external load(s)",
    "{} destek elemanı": "{} support element(s)",
    "püskürtme beton + hasır çelik kaplama": "shotcrete + wire mesh facing",
    "gerilme çatlağı": "a tension crack",
    "psödo-statik deprem yükü (kh = {})": "pseudo-static seismic load (kh = {})",
    "yeraltı suyu tablası": "a water table",
    " Modelde {} dikkate alınmıştır.": " The model includes {}.",
    "Yöntemlere göre kritik güvenlik sayıları": "Critical factors of safety by method",
    # results table
    "Yöntem": "Method",
    "Çıkış x [m]": "Exit x [m]",
    "Giriş x [m]": "Entry x [m]",
    "Merkez (x; y) [m]": "Centre (x; y) [m]",
    "Yüzey": "Surfaces",
    "Durum": "Status",
    "Kalın satır global minimumu gösterir. λ: ara-dilim kuvvet ölçek katsayısı (Spencer / GLE). Yüzey: aramada değerlendirilen yüzey sayısı.":
        "The bold row is the global minimum. λ: interslice force scale factor (Spencer / GLE). "
        "Surfaces: number of surfaces evaluated in the search.",
    "Güvenlik sayısı karşılaştırması": "Factor of safety comparison",
    # model
    "Model ve Geometri": "Model and Geometry",
    "Model {} bölge ve {} malzemeden oluşmaktadır. Dış sınır {} köşelidir; model x = {} – {} m aralığındadır.":
        "The model consists of {} region(s) and {} material(s). The external boundary has {} "
        "vertices; the model spans x = {} – {} m.",
    "Yeraltı suyu tablası tanımlıdır.": "A water table is defined.",
    "Gerilme çatlağı sınırı tanımlıdır.": "A tension crack boundary is defined.",
    "Analiz modeli: geometri, malzemeler, yükler ve destekler":
        "Analysis model: geometry, materials, loads and supports",
    "Malzeme özellikleri": "Material properties",
    "Malzeme": "Material",
    "Su": "Water",
    "Dayanım parametreleri": "Strength parameters",
    "Malzeme parametreleri (Mohr-Coulomb)": "Material parameters (Mohr-Coulomb)",
    "Malzeme parametreleri (genelleştirilmiş Hoek-Brown)":
        "Material parameters (generalized Hoek-Brown)",
    "Malzeme parametreleri (diğer dayanım modelleri)": "Material parameters (other strength models)",
    "Su etkisi yok": "No water",
    "YASS": "Water table",
    "YASS, H<sub>u</sub> = {}": "Water table, H<sub>u</sub> = {}",
    "Genelleştirilmiş Hoek-Brown": "Generalized Hoek-Brown",
    # settings
    "Analiz Ayarları": "Analysis Settings",
    "Yeraltı suyu tablası (YASS)": "Water table",
    "Ru katsayısı (Ru = {})": "Ru coefficient (Ru = {})",
    "Yok (kuru)": "None (dry)",
    "sol uç x = {} – {}": "left end x = {} – {}",
    "sağ uç x = {} – {}": "right end x = {} – {}",
    "B-spline, kontrol noktası sayısı {}": "B-spline, {} control points",
    "poligonal, ara köşe sayısı {}": "polyline, {} interior vertices",
    "Dairesel": "Circular",
    "Dairesel olmayan": "Non-circular",
    "konveks": "convex",
    "Kullanıcı tanımlı yüzey": "User-defined surface",
    "yarım sinüs": "half-sine",
    "sabit": "constant",
    "kırpılmış sinüs": "clipped sine",
    "trapez": "trapezoidal",
    "Yöntemler": "Methods",
    "Birim sistemi": "Units",
    "Metrik — kN, kPa, m": "Metric — kN, kPa, m",
    "Göçme yönü": "Failure direction",
    "Sağdan sola": "Right to left",
    "Soldan sağa": "Left to right",
    "Dilim sayısı": "Number of slices",
    "Tolerans / maks. iterasyon": "Tolerance / max. iterations",
    "GLE ara-dilim fonksiyonu": "GLE interslice function",
    "Kayma yüzeyi": "Slip surface",
    "Arama": "Search",
    "Diferansiyel evrim + Nelder-Mead (popülasyon {}, en çok {} nesil, çekirdek {})":
        "Differential evolution + Nelder-Mead (population {}, at most {} generations, seed {})",
    "Kayma sınırları": "Slope limits",
    "Tüm model": "Whole model",
    "Minimum kayan kütle derinliği": "Minimum sliding mass depth",
    "Kabul edilebilirlik kontrolü": "Admissibility check",
    "Açık (mα &lt; 0.2 ve negatif taban kayma direnci reddedilir)":
        "On (mα &lt; 0.2 and negative base shear resistance are rejected)",
    "Kapalı": "Off",
    "Boşluk suyu basıncı": "Pore water pressure",
    "Sismik katsayılar": "Seismic coefficients",
    "Gerilme çatlağı": "Tension crack",
    "Çatlak suyu %{} dolu": "Crack water {}% full",
    "Analiz ve arama parametreleri": "Analysis and search parameters",
    # loads and supports
    "Yükler, Destekler ve Kaplama": "Loads, Supports and Facing",
    "Dış yükler": "External loads",
    "düşey": "vertical",
    "yüzeye dik": "normal to surface",
    "Yayılı": "Distributed",
    "Tekil": "Line",
    "Tip": "Type",
    "Konum [m]": "Location [m]",
    "Büyüklük": "Magnitude",
    "Yön / açı": "Direction / angle",
    "Destek elemanları": "Support elements",
    "(kesme)": "(shear)",
    "aktif": "active",
    "pasif": "passive",
    "paralel": "parallel",
    "teğet": "tangent",
    "dik": "perpendicular",
    "Ad": "Name",
    "Aralık [m]": "Spacing [m]",
    "Kapasite [kN]": "Capacity [kN]",
    "Plaka [kN]": "Plate [kN]",
    "Kök [kN/m]": "Bond [kN/m]",
    "Kök boyu [m]": "Bond length [m]",
    "Uygulama": "Application",
    "Doğrultu": "Orientation",
    "Destek tipleri": "Support types",
    "Baş A (x; y) [m]": "Head A (x; y) [m]",
    "Uç B (x; y) [m]": "End B (x; y) [m]",
    "Boy [m]": "Length [m]",
    "Eğim [°]": "Inclination [°]",
    "Tekil destekler": "Individual supports",
    "x aralığı [m]": "x range [m]",
    "İlk [m]": "First [m]",
    "Adet": "Count",
    "Bulon / ankraj paternleri (şev yüzü boyunca eşit aralıklı)":
        "Bolt / anchor patterns (equally spaced along the slope face)",
    "Kaplama (püskürtme beton + hasır çelik)": "Facing (shotcrete + wire mesh)",
    "Hasır (A<sub>s</sub> [mm²/m])": "Mesh (A<sub>s</sub> [mm²/m])",
    "Kaplama tipleri": "Facing types",
    "Kaplama tipi": "Facing type",
    "Kaplama atamaları": "Facing assignments",
    "Kaplama kapasitesi T = τ·t + A<sub>s</sub>·f<sub>y</sub>; kayma yüzeyinin kaplamalı yüzeyden çıktığı/girdiği noktada yüzeye teğet ve kaymaya karşı uygulanır. Kaplama ağırlığı γ·t yüzey yükü olarak eklenir.":
        "Facing capacity T = τ·t + A<sub>s</sub>·f<sub>y</sub>; applied tangent to the slip "
        "surface, against sliding, where the slip surface exits/enters through the faced "
        "surface. The facing weight γ·t is added as a surface load.",
    "Gerilme çatlağı sınırı x = {} – {} m arasında tanımlıdır; çatlak suyu %{} doludur. Çatlak suyu itkisi V = ½·γ<sub>w</sub>·h<sub>w</sub>² göçme yönünde, h<sub>w</sub>/3 yükseklikte uygulanır.":
        "The tension crack boundary is defined between x = {} – {} m; the crack is {}% full of "
        "water. The water thrust V = ½·γ<sub>w</sub>·h<sub>w</sub>² acts in the failure "
        "direction at h<sub>w</sub>/3 height.",
    "Uç ankrajlı": "End anchored",
    "Enjeksiyonlu ankraj (tieback)": "Grouted tieback",
    "Zemin çivisi": "Soil nail",
    "Geotekstil": "Geotextile",
    "Geosentetik": "Geosynthetic",
    "Mikro kazık": "Micro-pile",
    # results
    "Analiz Sonuçları": "Analysis Results",
    "Hiçbir yöntemde geçerli bir çözüm bulunamadı.": "No method produced a valid solution.",
    "Kritik kayma yüzeyleri ve güvenlik sayıları": "Critical slip surfaces and factors of safety",
    "kayma merkezi FS konturları ve kritik yüzey": "slip centre FS contours and critical surface",
    "Yöntemlere göre kritik yüzeyler": "Critical surfaces by method",
    "Mobilize destek kuvvetleri": "Mobilised support forces",
    "Eleman": "Element",
    "L<sub>iç</sub> [m]": "L<sub>in</sub> [m]",
    "L<sub>dış</sub> [m]": "L<sub>out</sub> [m]",
    "Belirleyici": "Governing",
    "Uyg.": "Appl.",
    "Kritik yüzeyleri kesen destek ve kaplama elemanlarının kuvvetleri":
        "Forces of the supports and facings crossing the critical surfaces",
    "T: düzlem dışı aralığa bölünmüş kapasite (kN/m). Pasif uygulamada kuvvet dengede T/F olarak mobilize olur.":
        "T: capacity divided by the out-of-plane spacing (kN/m). With passive application the "
        "force is mobilised as T/F in the equilibrium.",
    "çekme kapasitesi": "tensile capacity",
    "kök sıyrılma": "bond pullout",
    "sıyrılma (dış)": "pullout (outside)",
    "sıyrılma (iç)": "pullout (inside)",
    "plaka + sıyrılma (iç)": "plate + pullout (inside)",
    "çekme dayanımı": "tensile strength",
    "sıyrılma": "pullout",
    "kazık kesme dayanımı": "pile shear strength",
    "kaplama (τ·t + As·fy)": "facing (τ·t + As·fy)",
    "Kritik yüzeylerde gerilme çatlağı": "Tension crack on the critical surfaces",
    "Derinlik [m]": "Depth [m]",
    "Gerilme çatlağı ve çatlak suyu itkisi": "Tension crack and crack water thrust",
    # appendices
    "Dilim Verileri": "Slice Data",
    "Global minimum kayma yüzeyinin ({}, FS = {}) {} dilimine ait veriler. α: taban açısı (göçme yönünde pozitif), c, φ: tabanda kullanılan dayanım parametreleri (Hoek-Brown için σ<sub>n</sub>' ≈ W/b − u ile anlık değerler).":
        "Data of the {2} slices of the global minimum slip surface ({0}, FS = {1}). α: base "
        "angle (positive in the failure direction), c, φ: strength used on the base "
        "(instantaneous values at σ<sub>n</sub>' ≈ W/b − u for non-linear models).",
    "x<sub>orta</sub> [m]": "x<sub>mid</sub> [m]",
    "y<sub>taban</sub> [m]": "y<sub>base</sub> [m]",
    "Dilim verileri": "Slice data",
    "Koordinatlar": "Coordinates",
    "Dış sınır": "External boundary",
    "Malzeme sınırı": "Material boundary",
    "Yeraltı suyu tablası": "Water table",
    "Gerilme çatlağı sınırı": "Tension crack boundary",
    "Merkez": "Centre",
    "Yarıçap": "Radius",
    "Çıkış / giriş x": "Exit / entry x",
    "Kritik daire": "Critical circle",
    "Kritik yüzey noktaları": "Critical surface points",
    "Bu rapor SlipSurfaceIQ LE {} ile otomatik olarak üretilmiştir. Sonuçlar girilen geometri, malzeme ve yükleme verilerine dayanır; mühendislik yargısıyla değerlendirilmesi ve doğrulanması kullanıcının sorumluluğundadır.":
        "This report was generated automatically with SlipSurfaceIQ LE {}. The results rely on the "
        "geometry, material and loading data entered; evaluating and verifying them with "
        "engineering judgement is the responsibility of the user.",
    # engine messages shown in the results table
    "Bishop yalnızca dairesel yüzeyler için geçerlidir.": "Bishop is valid for circular surfaces only.",
    "Bishop yalnızca dairesel yüzeyler için geçerlidir; dairesel olmayan aramada atlandı.":
        "Bishop is valid for circular surfaces only; skipped in the non-circular search.",
    "çözüm yok": "no solution",
    "Kabul edilebilir olmayan çözüm.": "Inadmissible solution.",
    "Kabul edilebilir kayma yüzeyi bulunamadı (uç aralıklarını ve geometriyi kontrol edin).":
        "No admissible slip surface found (check the end ranges and the geometry).",
}

CATALOG = Catalog(PDF_EN)
