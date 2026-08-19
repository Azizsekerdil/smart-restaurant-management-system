# Değişiklik Günlüğü

Bu projenin dikkate değer tüm değişiklikleri bu dosyada belgelenir.

Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) standardına,
sürümleme [Semantic Versioning](https://semver.org/lang/tr/) kurallarına uyar.

---

## [1.5.0] — 2026-08-19

İlk **public** sürüm için güvenlik sertleştirmesi, gizlilik düzeltmeleri ve
yayın belgeleri.

### Güvenlik — düzeltildi

- **Kimlik doğrulamasız hesap ele geçirme (kritik).** `/accounts/pin/gecis/`
  uç noktası oturum açmadan çağrılabiliyordu: kullanıcı adını bilen biri
  4 haneli PIN'i deneyerek doğrudan o kullanıcı olarak oturum açabiliyordu.
  Uç nokta artık kimlik doğrulanmış oturum ister, yalnızca `pos.use` yetkisi
  olan hesaplara geçişe izin verir ve parola değiştirme borcu olan hesabı
  reddeder.
- **PIN kaba kuvvet saldırısı.** PIN denemeleri sayılmıyordu. Yeni
  `apps.accounts.pin_security`: hedef kullanıcı adı ve istemci IP'si başına
  5 hatalı denemeden sonra 15 dakika kilit, artan gecikme ve denetim kaydı.
  Aynı kısıtlayıcı yetkili onayı (iptal/iade/indirim) PIN'ine de uygulanır.
- **Zayıf PIN politikası.** `1111`, `1234`, `4321` gibi tekrar/ardışık ve
  yaygın PIN'ler artık reddedilir.
- **Geçici parola ile serbest gezinme.** `must_change_password` yalnızca
  giriş ekranında bir uyarı üretiyordu; kullanıcı adres çubuğundan korumalı
  sayfalara girebiliyordu. Yeni `PasswordChangeRequiredMiddleware` her
  istekte uygular (API isteğine `password_change_required` kodlu 403 döner).
- **Geliştirme Merkezi varsayılanı.** `DEVCENTER_ENABLED` /
  `DEVCENTER_TERMINAL_ENABLED` artık **varsayılan olarak kapalıdır**. Önceki
  varsayılan "üretim değilse açık" idi ve `.env` dosyası olmayan her
  kurulumda kod çalıştırma yüzeyini sessizce açıyordu.
- **Bildirim bağlantısı enjeksiyonu.** `notify(url=...)` artık yalnızca
  uygulama içi göreli yol kabul eder; `javascript:`/`data:`/şema-göreli
  adresler reddedilir (kalıcı XSS'e karşı tek boğazda savunma).
- **NaN enjeksiyonu.** Fiyat simülasyonu `NaN`/`Infinity` girdisini sessizce
  kabul ediyor ve mali ekranda anlamsız sayı gösteriyordu; artık reddedilir.

### Gizlilik — düzeltildi

- **Sağlık verisi sızıntısı.** Alerji notu (KVKK m.6 / GDPR m.9) DRF
  seri hâline getiricisinde maskeleniyordu, ancak müşteri arama ucundan,
  müşteri kartı şablonundan ve POS adisyon panelinden **maskesiz**
  görülebiliyordu. Üçü de `customer.pii` yetkisine bağlandı. Uyarının
  varlığı servis güvenliği için görünür kalır; yalnızca metni kısıtlanır.
- **Rezervasyon API'si** misafir telefonunu ve alerji notunu maskesiz
  döndürüyordu (`reservation.view` tüm salon personelinde vardır); artık
  aynı `customer.pii` kuralına tabidir. Yazma yolu bozulmadı.
- Şablonlarda tek bir yerden sorulabilen `can_see_customer_pii` bağlamı
  eklendi; her ekranın kendi bayrağını koyması unutulduğunda sessiz
  sızıntıya dönüşüyordu.

### Değişti

- **Sabit demo parolası kaldırıldı.** `seed_demo` her çalıştırmada rastgele
  güçlü bir parola üretir ve bir kez yazdırır. Demo PIN'leri de kurulum
  başına farklıdır (tohumlanmış üreteç yerine `secrets`).
- **Sentetik demo iletişim verisi.** Telefonlar `0000` ile başlar
  (çevrilemez), e-postalar RFC 2606 `.invalid` alan adını kullanır
  (çözümlenemez).
- `.env.example` içindeki tüm anahtar alanları **boş**; yerel makine yolu ve
  yer tutucu anahtar değeri kaldırıldı.
- `has_secret()` yer tutucu değerleri artık "tanımlı" saymaz.
- Sunum ve README'deki sayılar `scripts/project_metrics.py` ile **depodan
  ölçülür**; elle yazılan sayı kalmadı. Ölçülemeyen değer için sayı
  uydurulmaz, o kart sunumdan düşer.
- Sunum PDF'i özgür lisanslı yazı tipi (DejaVu Sans → Bitstream Vera) tercih
  eder ve tescilli yazı tipine düşerse uyarır. Çıktı
  `docs/presentation/*_PUBLIC.*` altına üretilir.
- Ekran görüntüsü betiği tek kullanımlık, `customer.pii` yetkisi **açıkça
  reddedilmiş** bir hesapla çalışır; parola kaynak kodda tutulmaz ve görüntü
  alınmadan önce parola alanları DOM'dan kaldırılır.
- Yayın kapısı ve `.gitignore`, dahili çalışma malzemesini ad ad değil
  **desen** olarak engeller.

### Eklendi

- İngilizce `README.md` (Türkçe sürüm `README.tr.md`), `PRIVACY.md`,
  `AI_TRANSPARENCY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `docs/known-limitations.md`, `PUBLIC_RELEASE_MANIFEST.json`.
- `SECURITY.md` artık yalnızca sorumlu açıklama sürecidir; işletme
  sertleştirme listesi `docs/hardening-checklist.tr.md` dosyasına taşındı.
- `sbom.spdx.json` + `sbom.cdx.json`, `.github/dependabot.yml` ve genişletilmiş
  `.github/workflows/ci.yml` (gitleaks, secret taraması, SBOM, migration
  dry-run, yayın kapısı).
- Yeni gerileme testleri: `tests/test_pin_and_bootstrap_security.py`,
  `tests/test_pii_masking_regression.py`.

---

## [1.4.0] — 2026-08-18

Compliance katmanı (Faz F1 + F2): KVKK saklama sınırlaması, gizlilik
sertleştirmeleri ve public yayın kapısı.

### Eklendi

- `manage.py purge_expired_logs`: saklama süresi dolan kişisel veri
  alanlarını redakte eder (önizleme varsayılan, `--apply` + denetim kanıt
  kaydı). Süreler `.env` `RETENTION_*` değişkenleriyle tanımlanır;
  varsayılan kapalıdır (süre kararı işletme/DPO'nundur)
- `scripts/public_release_check.py`: depo public yapılmadan önce zorunlu
  teknik kapı (secret taraması, yasak dosya, .gitignore, lisans allowlist)
- Keşif ve plan belgeleri: `DISCOVERY_REPORT.md`, `HSP_PROJECT_REVIEW.md`,
  `IMPLEMENTATION_PLAN.md`, faz raporları
- `tests/test_compliance.py`: 33 test (maskeleme, izinler, saklama, yayın
  kapısı, JWT replay)

### Değiştirildi

- AI sohbet geçmişi (`AIConversationMessage`) artık PII/secret maskeli
  saklanır (kullanım kaydıyla aynı politika)
- Alerji notu yönetim API'sinde `customer.pii` iznine bağlandı; servis
  ekranlarında (adisyon/POS/rezervasyon) gıda güvenliği gereği görünür kalır
- Personel verisi içeren AI asistan bağlamı `sensitive=True` ile yalnızca
  yerel modele yönlendirilir
- JWT refresh rotasyonunda eski token kara listeye alınır
  (`token_blacklist` etkin; mevcut kurulumlar `manage.py migrate` çalıştırmalı)

### Eklendi (Faz F3)

- `docs/data_inventory.json`: makine-okunur kişisel veri envanteri (35 alan)
  + `apps/core/privacy.py` tarayıcısı. CI kapısı: envantersiz yeni kişisel
  veri alanı veya bayat envanter kaydı testleri kırar
- KVKK veri dosyası indirme (DSR erişim/taşınabilirlik): müşteri detay
  sayfasından JSON dışa aktarma — `customer.pii` izni + denetim kaydı
- `docs/ROPA_HAZIRLIK.md`: işleme faaliyetleri envanteri hazırlığı
  (7 faaliyet, DPO doğrulama listesi; resmî kayıt iddiası yok)

### Eklendi (Faz F4–F5)

- AI sağlayıcı governance metadata'sı: bölge/saklama/eğitimde-kullanım;
  bulut sağlayıcılarda doğrulanana kadar REVIEW_REQUIRED uyarısı
  (`.env` `*_GOV_*` değişkenleriyle işletme doğrular)
- Prompt kayıt defteri (`PROMPT_REGISTRY`): 17 sistem istemi sürümlü;
  kayıtsız istem CI'ı kırar
- AI içgörülerinde gerekçe-makbuzu: model, istem sürümü, veri noktası,
  güven ve dönem bilgisi içgörü ekranında gösterilir
- Public yayın kapısına HSP ana promptu kontrolü; `PUBLIC_RELEASE_READINESS.md`
  hazırlık raporu (durum: NOT_READY — tek engel ve seçenekleri belgelendi)

---

## [1.3.0] — 2026-08-15

Türkçe/İngilizce dil desteği ve uygulama içi eğitim modülü.

### Eklendi

**Çok dillilik**

- `UserLanguageMiddleware`: kullanıcının profilindeki dil tercihini uygular.
  Bu ara katman olmadan, ayarlardan İngilizce seçmek hiçbir işe yaramıyordu.
- Üst çubukta ve giriş ekranında dil değiştirici; seçim giriş yapmış
  kullanıcının profiline yazılır, anonim kullanıcıda çerezde tutulur
- `scripts/i18n_tools.py`: GNU gettext kurulumu gerektirmeyen çıkarma ve
  `.mo` derleme aracı (Windows'ta `xgettext`/`msgfmt` bulunmaz)
- `scripts/translations_en.py`: çevirilerin tek kaynağı, 938 girdi
- `locale/en/LC_MESSAGES/django.po` ve derlenmiş `.mo`

**Eğitim modülü (`apps/training`)**

- 3 öğrenme yolunda 8 ders: ilk adımlar, güvenlik alışkanlıkları, POS,
  mutfak ekranı, stok ve fire, istatistik okuma, yönetici rutini, yedekleme
- Dersler kullanıcının yetkisine göre filtrelenir
- Adım adım anlatım, uyarı/ipucu kutuları, ilgili ekrana bağlantı
- Ders sonunda kısa kontrol soruları; yanlış yanıtta ders tamamlanmaz
- Kişisel ilerleme takibi (`LessonProgress`) ve sıfırlama
- İçerik iki dilli; üst çubukta her sayfadan erişilebilen yardım düğmesi

### Düzeltildi

- **Geri yükleme başarılı olduğu hâlde kullanıcıya "Bad Request (400)"
  gösteriyordu.** Geri yükleme oturum tablosunu da yedekteki hâline
  döndürdüğü için, isteğin sonunda Django silinmiş oturum satırını
  güncellemeye çalışıp `SessionInterrupted` yükseltiyordu. Artık işlem
  sonrası oturum bilinçli olarak kapatılıp giriş ekranına yönlendiriliyor —
  kullanıcı hesapları da yedekteki hâline döndüğü için yeniden giriş zaten
  gereklidir.
- Çeviri çıkarıcısı `{% blocktrans %}` içindeki `{{ değişken }}` ifadelerini
  Django'nun kullandığı `%(değişken)s` biçimine çevirmiyordu; anahtar
  tutmadığı için o metinler sessizce çevrilmiyordu.
- Katalogdaki boş çeviriler, sözlükteki dolu çevirilerin üzerine yazıyordu.

### Bilinen sınırlama

- 92 şablonun 91'i işaretlidir. Geriye kalan ~89 metin, satır içi etiketlerle
  bölünmüş veya değişken içeren cümlelerdir ve çoğu yönetim/yapılandırma
  ekranlarındadır. Kapsam `python scripts/i18n_tools.py status` ile ölçülür.

---

## [1.4.0] — 2026-08-18

Tanıtım sunumu ve PDF çıktılarında Türkçe karakter düzeltmesi.

### Eklendi

- `sunum/` klasöründe iki dilli tanıtım seti — 16 slayt, 10 dosya:
  HTML (tarayıcıda gezinilebilir), PDF ve PPTX; her biri için ayrıca
  baskıya uygun açık zeminli sürüm.
- `scripts/presentation_content.py`: sunum içeriğinin tek kaynağı
  (Türkçe + İngilizce yan yana).
- `scripts/make_presentation.py`: aynı içerikten HTML, PowerPoint ve PDF
  üretir. Bir cümle değiştiğinde on dosya birden güncellenir.

### Düzeltildi

- **PDF çıktılarında Türkçe harfler kayboluyordu.** ReportLab'ın yerleşik
  Helvetica'sı WinAnsi kodlaması kullanır ve `ş ğ ı İ` harflerini
  içermez; "Satış Raporu" çıktıda "Sat■■ Raporu" olarak görünüyordu.
  `ç ö ü` WinAnsi'de bulunduğu için hata gözden kaçmıştı. Artık
  sistemden Türkçe destekli bir TrueType yazı tipi yükleniyor; hiçbiri
  bulunamazsa günlüğe uyarı yazılıp belge yine de üretiliyor.
  Bu satış raporu, gün sonu raporu ve adisyon fişlerinin tümünü
  etkiliyordu.
- Sunum üretiminde `str.upper()` Türkçe'de yanlış sonuç veriyordu
  ("önemli" → "ÖNEMLI"); dile duyarlı büyük harf eklendi.
- Sunum slaytlarında `overflow: hidden` dar ekranda içeriği sessizce
  kırpıyordu; slayt artık gerektiğinde uzuyor.

### Test

- PDF çıktısının Türkçe harfleri koruduğunu doğrulayan iki regresyon
  testi eklendi.

---

## [1.3.1] — 2026-08-15

Çeviri kapsamının tamamlanması.

### Eklendi

- `scripts/mark_templates.py`: şablonlardaki düz metinleri çeviri etiketiyle
  işaretleyen yardımcı araç. Yalnızca **güvenli** durumları dönüştürür:
  bir etiketin tüm içeriğini oluşturan metinler, `title`/`placeholder`/
  `aria-label`/`alt` öznitelikleri ve simge sonrası düğme etiketleri.
  `<script>`, `<style>`, `<code>`, `<pre>` ve değişken içeren cümlelere
  dokunmaz.
- Çeviri sayısı 938'den **1.759**'a çıktı; 88 şablon işaretlendi.

### Düzeltildi

- **Excel dışa aktarma, çevrilebilir etiketlerde çöküyordu.** `gettext_lazy`
  nesneleri gerçek `str` değildir ve openpyxl bunları reddeder; dışa aktarma
  katmanı artık değeri indirgiyor.
- İstatistik merkezindeki dönem seçenekleri, gün adları ve ölçüt etiketleri
  Python tarafında çeviri işaretlemesi taşımıyordu.

### Araç geliştirme sırasında yakalanan hatalar

Otomatik işaretleme üç kez geri alınıp düzeltildi; her biri gerçek bir
bozulmaydı:

1. **İç içe tırnak**: `title="{% trans "metin" %}"` HTML'i bozuyordu —
   öznitelik ilk iç tırnakta bitiyordu.
2. **Kod örneklerinin çevrilmesi**: `python manage.py migrate` her dilde
   aynıdır; `<code>` ve `<pre>` blokları atlanıyor.
3. **Şablon sözdizimi hatası**: satır içi `<code>` içeren cümleler
   `{% trans %}` dizesinin içine HTML kaçırıyordu.

---

## [1.2.0] — 2026-08-15

Uygulama içi yedekleme sistemi ve istatistik merkezi.

### Eklendi

**Yedekleme (`apps/backups`)**

- Uygulama içinden yedek alma: veritabanı + yüklenen dosyalar + taşınabilir
  JSON dökümü + manifest, tek ZIP arşivinde
- Tutarlı anlık görüntü: SQLite yedekleme API'si, PostgreSQL'de `pg_dump`
- SHA-256 ile bütünlük doğrulaması; arşiv içeriğini açmadan önizleme
- Geri yükleme: arşiv doğrulanır → **güvenlik yedeği alınır** → onay
  ifadesi istenir → veriler yazılır
- Geri yükleme sonrası yedek kayıtları diskle eşitlenir; güvenlik yedeği
  listede görünür kalır ve dönüş yolu kapanmaz
- Otomatik zamanlanmış yedekleme (hafif arka plan iş parçacığı) ve
  `manage.py backup_now [--if-due]` komutu
- Saklama politikası; güvenlik yedekleri sayı sınırına takılmaz
- Yeni izin kodları: `backup.view`, `backup.create`, `backup.download`,
  `backup.restore`

**İstatistik merkezi (`apps/reports/statistics.py`)**

- Seçilen dönemi önceki eşit dönemle karşılaştıran 8 ölçüt
- Günlük eğilim (önceki dönem aynı eksende) ve 12 aylık gidişat
- Gün × saat yoğunluk matrisi ve haftanın günleri ortalamaları
- Müşteri istatistikleri: yeni/tekrar eden, en değerli müşteriler
- Stok istatistikleri: fire oranı, tüketim, mevcut stok değeri
- Servis istatistikleri: ortalama servis süresi, masa devir hızı
- Çok sayfalı Excel dışa aktarma
- Yeni izin kodu: `report.statistics`

### Değiştirildi

- Az veriye dayanan istatistikler arayüzde **soluk gösterilir** ve kaç
  gözleme dayandığı yazılır; tek seferlik bir yoğunluk düzenli bir örüntü
  gibi sunulmaz
- Haftanın günleri toplam yerine **ortalama** üzerinden hesaplanır: bir gün
  aralıkta 4 veya 5 kez geçebilir, ham toplam yanıltıcıdır
- Servis süresi ortalamasında 8 saati aşan adisyonlar (kapatılması
  unutulmuş olanlar) elenir

### Düzeltildi

- **SQLite yedekleme çağrısı, veritabanı meşgulse süresiz bekliyordu.**
  Python'un `Connection.backup` çağrısı SQLITE_BUSY aldığında sonsuza
  kadar yeniden dener; çağıran kod bir `transaction.atomic` bloğunda
  olsaydı uygulama tamamen donardı. Kaynak için ayrı bir salt okunur
  bağlantı açılıyor ve ilerleme geri çağrısıyla süre sınırı uygulanıyor.
- Aynı saniyede alınan iki yedek aynı dosya adını üretiyordu.
- Testlerde SQLite bellekte çalıştığı için yedekleme kod yolu hiç
  sınanmıyordu; test veritabanı dosya tabanlı yapıldı.
- İstatistik sorgularında `quantity` takma adı model alanını gölgeliyordu
  (`services.py` içinde daha önce belgelenmiş tuzağın tekrarı).

### Güvenlik

- Yedek arşivi açılırken **zip slip** koruması: arşiv hedef klasörün
  dışına dosya yazamaz
- API anahtarları (`.env`) yedeğe varsayılan olarak **girmez**; açıkça
  izin verilirse arşiv "gizli ayarlar" olarak işaretlenir
- Yedek indirme ayrı bir izne bağlı ve denetim kaydına yazılıyor
- Geri yükleme ve silme, denetim kaydında **kritik** önem düzeyiyle

---

## [1.1.0] — 2026-08-15

Tek dosyalık Windows uygulaması (`.exe`) paketleme desteği.

### Eklendi

- `launcher.py` — paketlenmiş uygulamanın giriş noktası: veri klasörünü
  hazırlar, `.env` üretir, veritabanını taşır, ilk kurulum sihirbazını
  gösterir, Daphne (ASGI) sunucusunu başlatır ve tarayıcıyı açar
- `restaurant.spec` — PyInstaller yapılandırması (şablonlar, statik
  dosyalar, dinamik yüklenen Django uygulamaları, Channels/Twisted)
- `scripts/build_exe.ps1` — ikon üretimi → üretim ayarlarıyla
  `collectstatic` → paketleme adımlarını tek komutta yapar
- `scripts/install_app.ps1` — paketi kalıcı klasöre kurar, veritabanını
  koruyarak günceller, masaüstü/Başlat menüsü kısayollarını oluşturur
- `scripts/strip_sourcemaps.py` — vendor dosyalarındaki geçersiz kaynak
  harita referanslarını temizler
- `config/env.py` içinde `IS_FROZEN` ve `DATA_DIR`: paketlenmiş uygulamada
  yazılabilir veri exe'nin yanında tutulur, geçici açılma dizininde değil
- Port çakışmasında sağlık uç noktasıyla doğrulama; portu başka bir program
  tutuyorsa bir sonraki boş porta geçiş

### Düzeltildi

- **Paketlenmiş uygulama kurulum sırasında çöküyordu.** `seed_demo` çıktısı
  Windows'un Türkçe konsol kod sayfasında (cp1254/cp857) bulunmayan bir
  onay simgesi içeriyordu ve `UnicodeEncodeError` ile program kapanıyordu.
  Çıktı akışları hataya dayanıklı hale getirildi; komut çıktılarındaki
  süslü semboller ASCII karşılıklarıyla değiştirildi.
- `DEBUG=False` altında statik dosya manifestosu eksik olduğu için her
  sayfa hata veriyordu; `collectstatic` artık üretim ayarlarıyla çalışıyor
  ve manifest üretilmezse derleme duruyor.
- `scripts/create_shortcut.ps1` artık paketlenmiş sürümü otomatik seçiyor
  ve çalışma klasörünü hedefe göre ayarlıyor.

### Güvenlik

- Paketlenmiş sürümde AI Geliştirme Merkezi ve kontrollü terminal
  `IS_FROZEN` nedeniyle **zorla kapalı** (403 döner)
- `.gitignore`: `Uygulama/` ve `*.exe` eklendi — ikili dosyalar ve yanlarında
  oluşan veritabanı depoya girmez

---

## [1.0.0] — 2026-08-15

İlk kararlı sürüm.

### Eklendi

**POS ve sipariş**
- Dokunmatik ekrana uygun satış arayüzü, kategori filtreleme ve hızlı arama
- Masada servis, paket, gel-al ve kurye sipariş türleri
- Sipariş notu, porsiyon seçimi ve ekstra malzeme (modifier) desteği
- Hesap bölme: eşit, koltuk numarasına göre ve seçili ürünleri ayırma
- Adisyon birleştirme ve masalar arası taşıma
- Çoklu ödeme: nakit (para üstü hesabıyla), kart, yemek kartı, havale,
  online, sadakat puanı, hediye çeki, cari hesap
- Kupon ve elle indirim; yetkili PIN onaylı iptal, iade ve fiyat değiştirme
- 80 mm termal yazıcıya uygun fiş ve PDF adisyon

**Mutfak ekranı (KDS)**
- WebSocket tabanlı canlı KOT akışı (Django Channels)
- Siparişlerin hazırlık istasyonuna göre otomatik ayrılması
- Süre aşımında renk değişimi, yanıp sönme ve sesli uyarı
- Sırada → Hazırlanıyor → Hazır → Teslim edildi durum akışı
- Acil sıraya alma ve KOT yazdırma
- İstasyon bazlı hazırlık süresi performans raporu
- Bağlantı koptuğunda otomatik yeniden bağlanma ve yedek yoklama

**Stok ve reçete**
- Ölçü birimi dönüşümü (kg ↔ g, lt ↔ ml, koli ↔ adet)
- Parti (lot) bazlı stok, FIFO ve FEFO tüketim yöntemleri
- Son kullanma tarihi takibi ve yaklaşan tarih uyarısı
- Reçete (BOM) tanımı, fire oranı ve porsiyon verimi
- Sipariş mutfağa gönderildiğinde otomatik stok düşümü
- Stok bitince ürünü otomatik satışa kapatma, gelince geri açma
- Kritik seviye uyarısı ve tüketim hızına göre tükenme tahmini
- Stok sayımı, fark hesabı ve uygulama
- Fire/israf kayıtları, maliyet hesabı ve neden analizi
- Tedarikçi yönetimi, satın alma siparişi ve teslim alma
- Kritik stok için otomatik satın alma taslağı

**Salon ve rezervasyon**
- Görsel masa planı, masa durumları ve doluluk göstergesi
- Masa birleştirme ve garson atama
- Masaya özel QR menü kodu
- Rezervasyon takvimi, uygunluk kontrolü ve çakışma denetimi
- Bekleme listesi ve no-show kaydı

**Yetkilendirme**
- 12 rol ve 60+ işlev bazlı izin kodu
- Kullanıcı bazında ek izin verme ve rol iznini kapatma
- Hassas işlemlerde yetkili PIN onayı
- POS terminalinde PIN ile hızlı kullanıcı değişimi
- Değiştirilemez denetim kaydı

**Müşteri ve sadakat**
- Müşteri profili, tercih ve alerji notları
- Sadakat puanı, seviye sistemi ve puan hareketleri
- Segmentasyon ve kayıp riski göstergesi
- Kampanya ve kupon yönetimi
- Müşteri yorumları ve çözüm takibi
- KVKK rıza kaydı ve geri döndürülemez anonimleştirme

**Personel**
- Personel kayıtları, vardiya planlama ve puantaj
- İzin talebi ve onay akışı
- Görev listesi
- Satış performansı raporu

**Raporlama**
- Yönetim paneli: ciro, sipariş, ortalama sepet, doluluk, iptal/iade
- Günlük ciro grafiği ve saatlik yoğunluk analizi
- Ürün ve kategori kârlılığı (reçete maliyetine göre)
- Personel satış performansı ve ödeme yöntemi dağılımı
- İptal, indirim ve iade denetim raporu
- Kasa açılış/kapanış ve gün sonu özeti
- PDF, Excel (çok sayfalı) ve CSV dışa aktarma

**Yapay zekâ**
- Çok sağlayıcılı ağ geçidi: LM Studio, Ollama, NVIDIA NIM, OpenAI uyumlu,
  Anthropic, Google Gemini, OpenRouter
- Göreve göre model seçimi (genel, muhakeme, kod, matematik, görsel, gömme)
- Yerel öncelikli yönlendirme, otomatik yedekleme ve devre kesici
- Günlük/aylık USD bütçe sınırı ve token/maliyet takibi
- KVKK: istemde kişisel veri maskeleme, hassas görevlerde yerel model zorunluluğu
- Doğal dille rapor sorgulama (sistem verisiyle zenginleştirilmiş)
- Menü mühendisliği, talep tahmini, stok tükenme tahmini
- İsraf analizi, anormallik tespiti, personel ihtiyacı önerisi
- Fiyat simülasyonu, kampanya önerisi, günlük yönetici özeti
- Yorum duygu analizi ve menü açıklaması üretimi
- Muhakeme (reasoning) modellerinin `reasoning_content` alanı desteği

**AI Geliştirme Merkezi**
- Doğal dille kod değişikliği önerisi
- Diff önizlemesi ve zorunlu kullanıcı onayı
- Otomatik geri alma noktası ve ayrı Git dalı
- Test çalıştırma; testler başarısızsa uygulamayı reddetme
- Commit mesajı önerisi ve Git durum paneli
- Allowlist tabanlı güvenli terminal (6 katmanlı koruma)

**Arayüz**
- Bootstrap 5 tabanlı, açık/koyu temalı duyarlı tasarım
- Masaüstü, tablet ve mobil uyumluluk
- Klavye kısayolları ve erişilebilir renk kontrastı
- Bildirim merkezi
- Türkçe varsayılan dil, İngilizce için altyapı hazır
- Tüm ön yüz kütüphaneleri yerel paketli — internet gerektirmez

**Altyapı**
- Django 5.2, DRF, Channels
- SQLite (WAL) veya PostgreSQL
- Docker Compose yığını (PostgreSQL + Redis + ASGI)
- GitHub Actions: test, kalite, güvenlik ve Docker iş akışları
- Windows yardımcı scriptleri: kurulum, çalıştırma, test, yedekleme, geri yükleme
- 277 otomatik test

### Güvenlik

- django-axes ile brute-force koruması (5 deneme / 1 saat kilit)
- Parola politikası: 10+ karakter, karakter sınıfı çeşitliliği, tekrar denetimi
- CSP, Permissions-Policy ve güvenlik başlıkları
- Dosya yüklemede uzantı, boyut ve magic byte doğrulaması
- İstek hızı sınırlama (yol bazlı) ve DRF throttling
- Günlüklerde API anahtarı ve kişisel veri maskeleme
- Alt süreçlere gizli ortam değişkeni aktarılmaması
- Tüm bağımlılıklar `pip-audit` ile taranmış, bilinen açık yok

### Notlar

- Sistemin ürettiği fiş ve gün sonu raporları **yasal mali belge değildir.**
  ÖKC ve e-Fatura entegrasyonu için arayüz hazırlığı yapılmıştır.
- Yapay zekâ analizleri güven düzeyi, veri noktası sayısı ve sınırlamalarıyla
  birlikte sunulur; kesin sonuç olarak değerlendirilmemelidir.

---

## Sürüm planı

Planlanan geliştirmeler için [ROADMAP.md](ROADMAP.md) dosyasına bakın.
