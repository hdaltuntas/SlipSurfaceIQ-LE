# SlipSurface LE (Python) — 2026.0.0

2D Limit Denge (LEM) şev stabilite programı: Slide2 düzeninde native masaüstü
**Modeler** + ayrı **Yorumla** penceresi, doğrulanmış hesap motoru.

## 2026.0.0 — geri bildirim güncellemesi

- **Ekran çözünürlüğü**: Modeler ve Yorumla pencereleri ilk açılışta ekranın kullanılabilir
  alanını algılayıp o boyutta (ekranı kaplayan pencere) açılır; diyaloglar ekran
  çözünürlüğüne göre ölçeklenir ve ekrandan taşmaz. **F11** tam ekranı açar/kapatır.
- **Sonuç ekranı** (Slide2 düzeni): dairesel aramada denenen tüm dairelerin merkezlerinden
  **kayma merkezi FS kontur haritası** (her hücrede o merkezdeki en düşük FS), sağ üstte
  kademeli **FS lejantı** (0 … ≈6.4·FSmin+), kritik merkezde `FS = …` etiketi, merkeze
  kesikli çizgiler ve kesikli kritik yüzey. Görüntü Seçenekleri'nden konturlar, dilimler,
  kesikli çizgi ve tüm yüzeyler ayrı ayrı açılıp kapatılabilir.
- **Notlar / şekiller**: sonuç ekranında (ve Modeler'da) yazı, çizgi, ok, dikdörtgen ve
  elipsler şekline göre seçilir (çizgi/ok üzerine, dikdörtgen/elips içine tıklama),
  model çizgilerinin önünde öncelikli seçilir; seçili notta tutamaçlar ve kesikli çerçeve
  görünür; sağ tık menüsünde **Özellikler… / Notu sil** vardır.
- **Hesaplama penceresi**: yöntem (i/n), aşama (dairesel ön arama, diferansiyel evrim,
  Nelder-Mead, poligon köşe optimizasyonu, ara köşe ekleme), nesil, değerlendirilen /
  geçerli / reddedilen yüzey sayısı, en düşük ve son FS, dilim sayısı, geçen ve tahmini
  kalan süre ile zaman damgalı işlem günlüğü gösterilir.
- **İngilizce arayüz**: durum çubuğu mesajları, çizim ipuçları, uyarılar, belge ağacı,
  sağ tık menüleri, dilim verisi, Bilgi Görüntüleyici metin raporu ve **PDF raporu** dahil
  seçilen dilde gösterilir. Kullanıcının girdiği proje, malzeme ve destek adları çevrilmez.
- **Yeni malzeme modelleri** (Malzeme Özellikleri → Göçme kriteri):

  | Kod | Model | Dayanım |
  |---|---|---|
  | `SH` | SHANSEP | `su = max(su,min; S·σ′v·OCR^m)` — σ′v dilim tabanında W/b − u (toplam gerilme) |
  | `HS` | Hardening Soil | Göçme yüzeyi Mohr-Coulomb (c′, φ′); E50, Eoed, Eur, m, pref, Rf, ψ bilgi amaçlı saklanır |
  | `SS` | SANISAND | `sin φ = 3Mb/(6+Mb)`, `Mb = M·exp(−nb·ψ)`, `ψ = e − (ec0 − λc(p′/pat)^ξ)`, p′ ≈ σ′n |
  | `PC` | Power Curve (Slide2) | `τ = a(σ′n + d)^b + c` |
  | `BB` | Barton-Bandis | `τ = σ′n tan(φr + JRCn log10(JCSn/σ′n))`, ölçek düzeltmesi (L0, Ln), φ ≤ 70° |
  | `CN` | CNI Rock Mass | `τ = a·σc·((σn − T0)/σc)^n` (Cylwik vd. 2023, Slide2 değişkenleri), anlık φ ≤ 70° |
  | `HBD` | Hoek-Brown (mb, s, a) | mb, s, a doğrudan girilir (GSI'dan türetilmez) |

  Doğrusal olmayan modellerde çözücü σ′n iterasyonuyla anlık c, φ kullanır.
- **Yeni destek modelleri**: **Mikro kazık** (kazık kesme dayanımı / aralık; kayma
  yüzeyine teğet veya kazığa dik) ve **Geosentetik** (şerit kaplama oranı, ankraj: yok /
  şev yüzünde / gömülü uçta / her iki uçta; sıyrılma `2·C·∫(adezyon + σv·tan δ)ds`,
  σv = γ·derinlik). Enjeksiyonlu ankraj (grouted tieback) ve geotekstil önceden vardı.

## 2026.0.0 — ilk sürüm

- Sürüm düzeni: `yıl.ana.alt` (2026.0.0).
- **Görünüm → Dil / Language** ile Türkçe/İngilizce arayüz seçimi anında uygulanır.
  Açık proje, geri alma geçmişi ve sonuçlar korunur. Tema tercihi de aynı menüdedir;
  her iki tercih sonraki açılışlarda hatırlanır.
- Genel araçlarda QtAwesome üzerinden açık kaynak Material Design Icons,
  uygulama yazılarında Source Sans 3 kullanılır. Teknolojiler ve lisans bağlantıları
  **Yardım → Hakkında** bölümündedir. Özel geoteknik simgeler uygulamanın vektör çizimleridir.
- **Dosya → Örnekler** altında dokuz örnek bulunur: mevcut altı örneğe drenajsız kil,
  doğrusal olmayan kuvvet yasası ve psödo-statik sismik analiz eklenmiştir.
- Malzemeler: Mohr-Coulomb, Hoek-Brown, **Undrained/Tresca** (`UD`) ve
  **Power-law envelope** (`PL`). UD toplam gerilme yaklaşımında `τ = su` kullanır.
  PL için `τ = a·pa·(1 + max(σ′n, 0)/pa)^b`; `a ≥ 0`, `0 < b ≤ 1`, `pa > 0 kPa`.
  Yeni modeller, proje kaydı, hesap motoru, malzeme etiketleri ve raporlara dahildir.

### DXF

**Dosya → DXF İçe Aktar / Dışa Aktar** üzerinden 2B geometri aktarılır.
İçe aktarma mevcut modeli değiştirir; **Ctrl+Z** ile tamamı geri alınabilir.

| Katman | İçerik |
|---|---|
| `SS_EXTERNAL` | Tek kapalı dış sınır; alternatif olarak `0` katmanında tek kapalı polyline |
| `SS_MATERIAL` | Malzeme sınırları |
| `SS_WATER` | Tek su tablası polyline |
| `SS_CRACK` | Tek gerilme çatlağı polyline |
| `SS_SURFACE` | Tek kullanıcı kayma yüzeyi |
| `SS_SUPPORT` | Tekil desteklerin çizgileri (yalnızca dışa aktarma) |

LINE, LWPOLYLINE, POLYLINE, ARC ve SPLINE okunur; eğriler 1 cm toleransla
doğru parçalarına dönüştürülür. DXF birimleri metreye çevrilir; birimsiz çizimler
uyarıyla metre kabul edilir. Z=0 dışındaki geometri reddedilir. Atlanan nesneler
listelenir. DXF yalnızca geometri alışverişidir; malzeme dayanımları, yükler,
destek kapasiteleri ve analiz sonuçları için `.slp.json` kullanın.

### Python scripting

**Araçlar → Python scripting**: `.py` dosyası açın veya editörde kod yazın,
**Run / Apply** ile uygulayın. Kod `project` nesnesinin bir kopyasında çalışır;
doğrulama başarılıysa değişiklikler tek bir geri alınabilir işlem olur.
Hata halinde açık proje değişmez. Scriptler yerel Python yetkileriyle çalışır;
yalnızca güvendiğiniz kodları çalıştırın.

`project` üzerinde `external`, `material_boundaries`, `assignments`, `water_table`,
`tension_crack`, `materials`, `support_types`, `supports`, `support_patterns`,
`facing_types`, `facings`, `loads`, `seismic`, `methods`, `surfaces`, `annotations`
ve diğer proje alanları kullanılabilir. `MaterialSpec`, `SupportType`, `FacingType`,
`Project`, `empty_project` editörde hazırdır.

Tüm geometri, yük, destek, kaplama ve malzeme tanımlarını gösteren çalışır örnek:
[`examples/scripted_slope.py`](examples/scripted_slope.py).

İngilizce seçeneği arayüzü, uyarıları ve PDF/metin raporlarını kapsar. Kullanıcının
proje ve malzeme adları çevrilmez.

## Çalıştırma

Gereksinim: Python 3.10+ (önerilen 3.11–3.13).

### En hızlı yol
- **Windows:** `run_windows.bat` dosyasına çift tıklayın (ilk seferde `.venv` kurar).
- **Linux/macOS:** `./run_linux_mac.sh`

### IDE ile (`main.py`)
1. Klasörü IDE'de açın.
2. Sanal ortam oluşturup bağımlılıkları kurun:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
   pip install -r requirements.txt          # geliştirme/test için: requirements-dev.txt
   ```
3. **`main.py`**'yi açıp Run/Debug'a basın.

Spyder'da Run → Configuration → *Execute in an external system terminal* önerilir.

### Komut satırı
```bash
python main.py                                    # ekran boyutunda, boş proje
python main.py examples/ankrajli_yarma.slp.json   # proje dosyası
python main.py --example "Katmanlı şev + YASS"    # paketteki örnek
python main.py --list-examples
python main.py --check                            # bağımlılık kontrolü
```
`main.py` hangi klasörden çalıştırılırsa çalıştırılsın proje klasörünü bulur; kurulum gerekmez.
İsteğe bağlı paket kurulumu: `pip install -e .` → `slipsurface` komutu ve `python -m slipsurface`.

### Testler
Qt testleri otomatik olarak başsız modda çalışır; pencere açılmaz.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -p no:cacheprovider --durations=15
python -m ruff check .
python -m mypy
```

Güncel test sayısı için `python -m pytest --collect-only` kullanın. Tam paket,
dairesel olmayan yüzey araması ve PDF/arayüz testleri nedeniyle birkaç dakika
veya daha uzun sürebilir. `--durations=15` en yavaş testleri listeler.
GitHub Actions, Windows ve Linux üzerinde testleri; ayrıca Ruff ve hesap
motorunun mypy kontrollerini çalıştırır.

## Arayüz

**Modeler**
- Menüler: Dosya, Düzen, Görünüm, Analiz, Sınırlar, Yükleme, Destek, Yüzeyler, Özellikler, Araçlar, Yardım
- İş akışı şeridi: Geometri › Destek › Yükleme › Özellikler › Yüzeyler (adıma göre araç çubuğu değişir)
- Sol panel: Belge Görüntüleyici (malzemeler, sınırlar, yöntemler) + Görüntü Seçenekleri
- Diyaloglar: Proje Ayarları (Genel, Yöntemler, Yeraltı Suyu, Sismik, Gelişmiş),
  Proje Özeti, Malzeme Özelliklerini Tanımla (MC / Hoek-Brown, su parametreleri),
  Yüzey Seçenekleri (dairesel / dairesel olmayan / kullanıcı tanımlı, kayma sınırları),
  Koordinat tablosu, Izgara ayarları
- Hesapla (F5) → sonuçlar otomatik olarak **Yorumla** penceresinde açılır
- **Malzeme etiketleri** (Görünüm → Malzeme Etiketleri veya Görüntü Seçenekleri):
  bölgelerin üzerinde yok / ad / ad + parametreler (c, φ, γ; Hoek-Brown için σci, GSI, mi, D)
- **Tekil bulon/ankraj** (Destek adımı): eğim (varsayılan **15°**) ve boy girilir,
  şev yüzüne tıklanır → başlık zeminde, doğrultu şevin içine otomatik
- **Bulon paterni** (grup): şev yüzünde iki nokta → aralık, ilk bulon mesafesi, eğim, boy;
  bulonlar yüzey boyunca eşit aralıkla otomatik üretilir, patern tek nesne olarak düzenlenir
- **Kaplama: püskürtme beton + hasır çelik** (Özellikler adımı): kalınlık, γ, τ,
  hasır (Q106…Q589 veya özel As), fy; şev yüzüne iki noktayla veya
  "Kaplamayı Şev Yüzüne Ata" ile topuk–kret arasına tek tıkla atanır
- **Notlar**: yazı, çizgi, ok, dikdörtgen, elips (sürükle = taşı, çift tık = özellikler)

**CAD çizim alanı**
- Cetveller, uyarlamalı ızgara, artı imleç, lejant
- Tekerlek = imleçte zoom, orta tuş = kaydır, orta çift tık / F2 = tümünü göster,
  pencereyle zoom, kaydır aracı
- **SNAP** (F9, ızgaraya), **GRID** (F7), **ORTHO** (F8), **OSNAP** (F3: uç, orta, kesişim, en yakın)
- Koordinat komut kutusu: `x,y` · `@dx,dy` · `@uzunluk<açı` · `c` kapat · `u` geri al · boş Enter bitir
- Çizim: dış sınır (kapalı), malzeme sınırları, YASS, kullanıcı tanımlı yüzey
- Düzenleme: köşe sürükle, köşe ekle/sil, çift tık = koordinat tablosu, Delete, sağ tık menüsü
- Bölgeye tıklayarak malzeme ata; bölgeler sınırlardan otomatik oluşturulur
- Geri al / yinele (Ctrl+Z / Ctrl+Y) — tüm düzenlemeler için

**Yorumla**
- Yöntem seçici ("Bishop simplified FS: 1.197"), Global Minimum
- Kritik yüzey, dilimler, merkeze çizgiler, FS kutusu, FS renk skalalı en düşük 25 yüzey
- Dilim verisi sorgusu, Bilgi Görüntüleyici (metin raporu, kaydet/kopyala), resim dışa aktarma
- **FS lejantı** (sağ alt): hesaplanan tüm yöntemlerin güvenlik sayıları, seçili yöntem
  vurgulu, global minimum yeşil
- Sonuç ekranına **yazı ve şekil** ekleme (kendi geri al/yinele'si; dosyaya kaydedilir)
- **PDF Rapor** (Ctrl+P; Yorumla → Dosya veya Modeler → Analiz): kapak (kritik FS kartı,
  hedef FS'ye göre Yeterli / Sınırda / Yetersiz), içindekiler, özet, model şekli,
  malzeme tabloları, analiz ayarları, yük / destek / kaplama tabloları, sonuç tablosu,
  FS karşılaştırma grafiği, kritik yüzey şekilleri (eksenli, yüksek çözünürlüklü),
  mobilize destek kuvvetleri, Ek: dilim verileri ve koordinatlar; sayfa üst/alt bilgisi,
  "Sayfa n / N", PDF yer imleri. Hazırlayan / kontrol eden / firma bilgileri hatırlanır.

## Hesap motoru

| Yöntem | Denge | Yüzey |
|---|---|---|
| Bishop simplified | moment | dairesel |
| Ordinary/Fellenius | moment (daire) / kuvvet | her ikisi |
| Janbu simplified / corrected (f0) | kuvvet | her ikisi |
| Corps of Engineers #1, #2 | kuvvet | her ikisi |
| Lowe-Karafiath | kuvvet | her ikisi |
| Spencer | kuvvet + moment | her ikisi |
| GLE / Morgenstern-Price (yarım sinüs, sabit, kırpılmış sinüs, trapez) | kuvvet + moment | her ikisi |

- Malzeme: Mohr-Coulomb, genelleştirilmiş Hoek-Brown, Hoek-Brown (mb, s, a), Undrained,
  SHANSEP, Hardening Soil, SANISAND, Power-law, Power Curve, Barton-Bandis, CNI
  (doğrusal olmayanlarda anlık c, φ — σn′ iterasyonu)
- Boşluk suyu: YASS (malzeme bazında Hu ve aç/kapa), Ru katsayısı; γsat
- Psödo-statik sismik: kh (göçme yönünde), kv (yukarı pozitif)
- Gerilme çatlağı: çatlak çizgisi (çizilerek veya derinlikten, Rankine z_c önerisiyle);
  kayma yüzeyi çizgiyi kret tarafında kestiği yerde kesilir, düşey çatlak yüzü oluşur;
  çatlak suyu kuru / dolu / % → V = ½ γw hw², göçme yönünde, hw/3 yükseklikte
- Dış yükler: yayılı (üniform / doğrusal değişen; düşey veya yüzeye dik), tekil (açılı)
- Destekler: uç ankrajlı, enjeksiyonlu ankraj (tieback), zemin çivisi, geotekstil,
  geosentetik, mikro kazık;
  kuvvet = kapasite / sıyrılma (L_iç, L_dış), aralık; **aktif** (doğrudan) veya **pasif** (T/F);
  doğrultu desteğe paralel veya kayma yüzeyine teğet. Tüm yöntemlere dahil
  (Bishop/Fellenius moment, GLE/Spencer kuvvet + moment, kuvvet yöntemleri)
- Kaplama (püskürtme beton + hasır çelik): ağırlığı γ·t yüzey yükü olarak eklenir;
  kayma yüzeyi kaplamalı yüzeyden çıkıyor/giriyorsa T = τ·t + As·fy kayma yüzeyine teğet,
  kaymaya karşı (varsayılan pasif, T/F) uygulanır
- Bulon paterni: her bulon ayrı destek olarak tüm yöntemlere dahil edilir
- Göçme yönü: sağdan sola / soldan sağa (zorunlu)
- Kritik yüzey araması: diferansiyel evrim + Nelder-Mead; dairesel ön arama ile
  tohumlanmış popülasyon; kayma sınırları; minimum derinlik
- Dairesel olmayan yüzey: **poligonal** (Slide2 gibi doğru parçaları; varsayılan) veya
  yumuşak B-spline. Poligonal aramada en iyi yüzeyin tüm köşeleri serbestçe optimize
  edilir, ardından her segmente ara köşe eklenip tekrar iyileştirilir
- Kabul edilebilirlik: mα < 0.2 ve negatif taban kayma direnci olan çözümler reddedilir

### Doğrulama (testlerde)
- ACADS EX1(a): Bishop 0.985, Spencer 0.984, GLE 0.984 (Slide2: 0.987 / 0.986 / 0.986)
- Düzlemsel blok: tüm kuvvet dengesi yöntemleri rijit blok kapalı çözümünü sismik
  yükle, dış yüklerle, aktif ve pasif ankrajla (F'de ikinci derece denklem) 10⁻⁶ hassasiyetle verir
- Hoek & Bray düzlemsel kayma + düşey gerilme çatlağı (kuru / yarı dolu / dolu): 7 yöntem, 10⁻⁶
- Bishop–GLE moment tutarlılığı (yükler, pasif ankraj ve çatlak suyu dahil), destek kapasite formülleri
- Ayna simetrisi, bağımsız Bishop referansı, sonsuz şev limiti, ağırlık = alan × γ

## Klasör yapısı

```
main.py           IDE / komut satırı giriş noktası
pyproject.toml    paket tanımı (pip install -e .)
requirements*.txt bağımlılıklar
run_windows.bat, run_linux_mac.sh   tek tık kurulum + çalıştırma
slipsurface/
  geometry/   slope.py, surfaces.py (daire, polyline, B-spline), builder.py (sınırlardan bölgeler)
  materials/  Mohr-Coulomb, Hoek-Brown
  lem/        slicing.py, bishop.py, gle.py (Spencer, GLE, Janbu, Corps, Lowe-Karafiath)
  optimizer/  search.py (DE + Nelder-Mead, daire / B-spline)
  loads.py    dış yükler, destek kuvvetleri, kaplama, bulon yerleşimi
  project.py  proje modeli, JSON (v3; v1/v2 dosyalar otomatik açılır)
  analysis.py çok yöntemli çalıştırıcı, metin raporu
  report/     pdf.py (ReportLab PDF raporu), fonts/ (Source Sans 3, SIL OFL)
  ui/         modeler.py, interpret.py, docks.py, workflow.py, statusbar.py, icons.py,
              document.py (geri al), worker.py, cad/ (canvas, rulers, tools), dialogs/
examples/     *.slp.json
tests/
```

## Durum

- [x] Adım 1–5: iskelet, pencere, geometri, Bishop, buton → kritik daire
- [x] Adım 6: proje modeli ve kaydet/aç
- [x] Adım 7: Spencer, GLE/M-P (+ Janbu, Corps, Lowe-Karafiath)
- [x] Adım 8: arama seçenekleri, B-spline (dairesel olmayan) yüzeyler, kayma sınırları
- [x] Slide2 tarzı arayüz: CAD alanı, iş akışı, diyaloglar, ayrı Yorumla penceresi
- [x] Yükleme (yayılı, tekil, sismik) ve Destek (ankraj, tieback, çivi, geotekstil)
- [x] Gerilme çatlağı (kuru / dolu / kısmi su)
- [x] v0.5: FS lejantı, sonuç ekranında not/şekil, malzeme etiketleri, püskürtme beton +
      hasır çelik kaplama, 15° tekil bulon/ankraj, bulon paterni
- [x] v0.6: PDF rapor, poligonal dairesel olmayan yüzey, sonuç ekranında kontrol noktaları gizli
- [ ] Sonraki: olasılıksal analiz (Monte Carlo), Sarma, geri analiz

## Lisans

Copyright © 2026 Hasan Deniz Altuntaş.

SlipSurface LE, [GNU Affero Genel Kamu Lisansı sürüm 3](LICENSE) (AGPL-3.0) veya (tercihinize göre)
daha sonraki bir sürümü altında dağıtılan özgür yazılımdır. Program **hiçbir garanti
olmaksızın** sunulur; sonuçların mühendislik yargısıyla değerlendirilmesi ve
doğrulanması kullanıcının sorumluluğundadır. Programı değiştirip bir ağ üzerinden
(ör. sunucu / web hizmeti olarak) kullanıcılara sunarsanız, AGPL gereği değiştirilmiş
kaynak kodunu da bu kullanıcılara sağlamanız gerekir. Kullanılan üçüncü taraf bileşenlerin
lisansları **Yardım → Hakkında** bölümünde listelenir (Qt/PySide6: LGPL-3.0,
NumPy/SciPy/Shapely: BSD, ReportLab: BSD, ezdxf ve QtAwesome: MIT, Material Design
Icons: Apache-2.0, Source Sans 3: SIL OFL 1.1).
