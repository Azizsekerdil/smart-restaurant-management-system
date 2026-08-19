# 🍽️ Akıllı Restaurant Yönetim Sistemi (Türkçe)

Restoranın tamamını tek yerden yöneten, **yapay zekâ destekli** açık kaynak
yönetim sistemi. POS, masa planı, mutfak ekranı (KDS), reçete bazlı stok
takibi, rezervasyon, müşteri sadakati, personel yönetimi ve mali raporlama
tek uygulamada toplanır.

Yapay zekâ katmanı **hem yerel (LM Studio / Ollama) hem de bulut** modellerle
çalışır. Yerel model kullanıldığında hiçbir veri bilgisayarınızdan çıkmaz ve
sistem **internet olmadan** da tam işlevlidir.

[![Testler](https://github.com/Azizsekerdil/smart-restaurant-management-system/actions/workflows/ci.yml/badge.svg)](https://github.com/Azizsekerdil/smart-restaurant-management-system/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Django](https://img.shields.io/badge/django-5.2-092E20)
![Lisans](https://img.shields.io/badge/lisans-MIT-green)

---

## İçindekiler

- [Amaç](#amaç)
- [Öne çıkan özellikler](#öne-çıkan-özellikler)
- [Ekran görüntüleri](#ekran-görüntüleri)
- [Sistem gereksinimleri](#sistem-gereksinimleri)
- [Windows kurulumu (5 dakika)](#windows-kurulumu-5-dakika)
- [Geliştirme kurulumu](#geliştirme-kurulumu)
- [Tanıtım sunumu](#tanıtım-sunumu)
- [Uygulamayı paketleme (.exe)](#uygulamayı-paketleme-exe)
- [Docker ile kurulum](#docker-ile-kurulum)
- [LM Studio kurulumu (yerel yapay zekâ)](#lm-studio-kurulumu-yerel-yapay-zekâ)
- [NVIDIA NIM kurulumu (bulut yapay zekâ)](#nvidia-nim-kurulumu-bulut-yapay-zekâ)
- [Yönetici hesabı oluşturma](#yönetici-hesabı-oluşturma)
- [Demo veri ve giriş bilgileri](#demo-veri-ve-giriş-bilgileri)
- [Test komutları](#test-komutları)
- [Güvenlik notları](#güvenlik-notları)
- [Belgeler](#belgeler)
- [Lisans](#lisans)

---

## Amaç

Küçük ve orta ölçekli restoranların çoğu; adisyonu bir programda, stoğu Excel'de,
personeli deftere yazarak yönetir. Bu dağınıklık üç şeye mal olur: **kaçak
maliyet**, **görülmeyen israf** ve **geç kalınmış karar**.

Bu proje, bu üç sorunu tek bir veri modeliyle çözer:

- Bir sipariş mutfağa gittiği anda **reçetesine göre stok otomatik düşer** —
  ayrı bir stok kaydı tutmanıza gerek kalmaz.
- Her ürünün **gerçek maliyeti ve kâr marjı** anlık olarak bilinir; menü kararı
  tahminle değil sayıyla verilir.
- Yapay zekâ katmanı bu verileri okur ve "hangi ürün zarar ettiriyor",
  "yarın kaç kişi bekleyebilirim", "bu iptaller normal mi" gibi sorulara
  **kendi verinizle** yanıt verir.

---

## Öne çıkan özellikler

### 🧾 POS ve sipariş
Dokunmatik ekrana uygun satış arayüzü · masada servis, paket, gel-al ve kurye
siparişleri · sipariş notu ve ekstra malzeme seçenekleri · **hesabı eşit,
koltuğa veya ürüne göre bölme** · adisyon birleştirme · masalar arası taşıma ·
çoklu ödeme (nakit, kart, yemek kartı, havale, sadakat puanı) · kupon ve elle
indirim · yetkili PIN onaylı iptal/iade · yazdırılabilir fiş ve PDF adisyon.

### 🔥 Mutfak ekranı (KDS)
Siparişler **istasyona göre otomatik ayrılır** (sıcak mutfak, ızgara, soğuk
mutfak, bar, tatlı) · WebSocket ile canlı akış, sayfa yenilemeye gerek yok ·
süre aşımında renk değişimi ve sesli uyarı · KOT yazdırma (80 mm termal
uyumlu) · istasyon bazlı hazırlık süresi performans raporu.

### 📦 Stok ve reçete
Malzeme kartları ve **birim dönüşümü** (kg ↔ g, lt ↔ ml, koli ↔ adet) ·
**parti (lot) bazlı FIFO/FEFO tüketimi** · son kullanma tarihi takibi ·
reçeteye göre otomatik düşüm (fire oranı dahil) · **stok bitince ürünü
otomatik satışa kapatma, stok gelince geri açma** · kritik seviye uyarısı ·
tüketim hızına göre tükenme tahmini · sayım ve fark uygulama · fire/israf
kayıtları · tedarikçi ve satın alma siparişi · kritik stok için otomatik
sipariş taslağı.

### 🪑 Salon ve rezervasyon
Sürüklenebilir görsel masa planı · masa durumu (boş/dolu/rezerve/temizlikte) ·
masa birleştirme · garson atama · **masaya özel QR menü** · rezervasyon takvimi,
uygunluk kontrolü, bekleme listesi, no-show kaydı.

### 👥 Yetkilendirme
**12 rol** (işletme sahibi, genel müdür, restoran müdürü, şef, mutfak
personeli, şef garson, garson, kasiyer, bar personeli, depo/satın alma,
muhasebe, kurye) ve **60+ işlev bazlı izin**. Kullanıcı bazında ek izin verme
veya rol iznini kapatma. Hassas işlemlerde yetkili PIN onayı.

### 📊 Raporlama
Yönetim paneli (ciro, sipariş, ortalama sepet, doluluk, iptal/iade oranı) ·
saatlik yoğunluk · ürün ve kategori kârlılığı · personel satış performansı ·
ödeme dağılımı · iptal/indirim/iade denetim raporu · kasa açılış-kapanış ve
gün sonu özeti · **PDF, Excel ve CSV dışa aktarma**.

### 🌍 Türkçe / İngilizce

- Üst çubuktan tek tıkla dil değişimi; seçim **hesaba kaydedilir**, başka
  cihazda da geçerlidir
- Giriş ekranında da dil seçilebilir (henüz hesap yokken çerezde tutulur)
- **1.759 metin çevrildi**: alan adları, seçim listeleri, doğrulama mesajları,
  gezinti menüsü, üst çubuk, tüm ekran başlıkları, düğmeler, tablo başlıkları,
  boş durum metinleri ve eğitim modülü
- GNU gettext kurulumu **gerekmez**: `.po` çıkarma ve `.mo` derleme araçları
  saf Python ile depoda (`scripts/i18n_tools.py`)
- Şablon işaretlemesi için yardımcı araç: `scripts/mark_templates.py`

> **Kapsam dürüstlüğü:** 92 şablonun 91'i işaretlidir. Geriye kalan yaklaşık
> 89 metin, satır içi etiketlerle bölünmüş veya değişken içeren cümlelerdir ve
> çoğu yönetim/yapılandırma ekranlarındadır (AI sağlayıcı ayarları, geliştirme
> merkezi). Günlük kullanılan ekranlarda (panel, POS, mutfak, stok, raporlar,
> istatistik, yedekleme, eğitim) İngilizce arayüzde kalan Türkçe metin
> yalnızca **verinizin kendisidir** (ürün, personel, kategori adları).
> Kapsamı ölçmek için: `python scripts/i18n_tools.py status`

### 🎓 Eğitim modülü (uygulama içi kılavuz)

- 8 ders, 3 öğrenme yolunda: Başlangıç · Servis ve mutfak · Yönetim
- Dersler **yetkiye göre filtrelenir** — garsona yedekleme dersi gösterilmez
- Adım adım anlatım, uyarı ve ipucu kutuları, ilgili ekrana doğrudan bağlantı
- Her dersin sonunda kısa kontrol soruları; yanlış yanıtta ders tamamlanmaz,
  açıklamayı okuyup tekrar denersiniz
- Kişisel ilerleme takibi ve sıfırlama
- İçerik iki dilli; üst çubuktaki **?** düğmesinden her yerden erişilir

### 💾 Yedekleme ve geri yükleme

- Uygulama içinden tek tıkla yedek: veritabanı + yüklenen dosyalar + taşınabilir
  JSON dökümü tek arşivde
- Tutarlı anlık görüntü (SQLite yedekleme API'si / `pg_dump`) — çalışan sistemde
  bile yarım kopya oluşmaz
- SHA-256 ile bütünlük doğrulaması ve arşiv içeriğinin önizlemesi
- Geri yükleme öncesi **otomatik güvenlik yedeği**; onay ifadesi olmadan
  çalışmaz, her adım denetim kaydına yazılır
- Otomatik zamanlanmış yedekleme (veya `backup_now` komutuyla Görev Zamanlayıcı)
- Saklama politikası, eski yedeklerin otomatik temizliği
- API anahtarları **varsayılan olarak yedeğe girmez**

### 📈 İstatistik merkezi

- Seçilen dönemi önceki eşit dönemle karşılaştıran 8 ölçüt
- Gün × saat yoğunluk matrisi — personel planlaması için
- Haftanın günlerine göre ortalama performans (toplam değil: eşit karşılaştırma)
- Müşteri davranışı: yeni/tekrar eden oranı, en değerli müşteriler
- Fire, tüketim ve stok değeri; servis hızı ve masa devir hızı
- Az veriye dayanan hücreler **soluk gösterilir** — tek seferlik bir yoğunluk
  düzenli bir örüntü gibi okunmaz
- Tüm bölümlerin çok sayfalı Excel çıktısı

### 🤖 Yapay zekâ
- **Doğal dille rapor sorgulama** — "Bugün en çok hangi ürün satıldı?"
- **Menü mühendisliği** — ürünleri yıldız / işçi / bulmaca / düşük performans
  olarak sınıflandırır
- **Talep tahmini** — haftanın gününe göre aralıklı tahmin
- **İsraf analizi** — fire nedenlerinin kök neden değerlendirmesi
- **Anormallik tespiti** — olağandışı iptal/indirim örüntüleri
- **Personel ihtiyacı önerisi** · **fiyat simülasyonu** · **kampanya önerisi**
- **Yorum duygu analizi** · **menü açıklaması üretimi** · **günlük yönetici özeti**

> Sayısal hesapların tamamı **deterministik Python koduyla** yapılır; yapay
> zekâ yalnızca sonucu yorumlar. Böylece hiçbir rakam modelin uydurmasına bağlı
> olmaz ve **AI erişilemese bile analizler çalışmaya devam eder.**

### 🛠️ AI Geliştirme Merkezi
Uygulamanın içinden, yalnızca yetkili rollere açık geliştirme ortamı: doğal
dille kod değişikliği isteme · **diff önizlemesi ve onay** · otomatik geri
alma noktası · ayrı Git dalı · test çalıştırma · commit mesajı önerisi ·
**allowlist tabanlı güvenli terminal**.

---

## Ekran görüntüleri

Aşağıdaki ekranları `docs/screenshots/` klasörüne ekleyebilirsiniz:

| Ekran | Dosya | Açıklama |
|---|---|---|
| Yönetim paneli | `dashboard.png` | Ciro, doluluk, uyarılar, grafikler |
| POS | `pos.png` | Dokunmatik satış ekranı ve adisyon paneli |
| Mutfak ekranı | `kds.png` | İstasyon bazlı canlı KOT akışı |
| Masa planı | `floor.png` | Görsel salon düzeni |
| Stok | `inventory.png` | Kritik seviye ve parti takibi |
| Kârlılık | `profitability.png` | Ürün bazlı marj analizi |
| AI asistanı | `ai-assistant.png` | Doğal dille rapor sorgulama |
| Geliştirme merkezi | `devcenter.png` | Diff onayı ve güvenli terminal |

Ekran görüntüsü almak için: uygulamayı çalıştırın, `python manage.py seed_demo`
ile demo veriyi yükleyin ve ilgili sayfaları kaydedin.

---

## Sistem gereksinimleri

| Bileşen | Asgari | Önerilen |
|---|---|---|
| İşletim sistemi | Windows 10 / 11, Linux, macOS | Windows 11 |
| Python | 3.11 | 3.12 |
| RAM | 4 GB | 8 GB+ |
| Disk | 2 GB | 5 GB |
| Veritabanı | SQLite (dahili) | PostgreSQL 14+ |
| Tarayıcı | Chrome / Edge / Firefox güncel sürüm | — |

**Yerel yapay zekâ için ek olarak:** LM Studio ve 8 GB+ VRAM'li bir GPU
(veya 16 GB+ RAM ile CPU üzerinde daha yavaş çalışır). Yapay zekâ **isteğe
bağlıdır** — kurulmazsa sistem tüm restoran işlevleriyle normal çalışır.

---

## Windows kurulumu (5 dakika)

### En kolay yol — tek dosyalık uygulama (.exe)

Python kurulumu, sanal ortam, komut satırı gerekmez. Uygulamayı paketleyip
masaüstüne kısayol koyar:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_app.ps1 -StartMenu
```

Masaüstündeki **Akıllı Restaurant** kısayoluna çift tıklayın. Program ilk
açılışta veritabanını hazırlar ve size sorar:

1. Örnek veriyle dene (menü, stok, 30 günlük satış geçmişi)
2. Boş başla, yalnızca yönetici hesabı oluştur
3. Atla

Ardından tarayıcı `http://127.0.0.1:8000` adresinde kendiliğinden açılır.

> **Veriniz nerede?** Veritabanı, günlükler ve yüklenen dosyalar exe'nin
> **yanındaki** klasörde (`Uygulama\`) tutulur. Yedek almak için bu klasörü
> kopyalamanız yeterlidir. Uygulamayı taşımak isterseniz klasörün tamamını
> taşıyın.

> **Not:** Paketlenmiş sürümde AI Geliştirme Merkezi ve kontrollü terminal
> kapalıdır — bunlar geliştirme ortamına özgüdür.

Ayrıntılar: **[INSTALL_WINDOWS.md](INSTALL_WINDOWS.md)**

### Kaynaktan kurulum — hazır script

```powershell
cd D:\Restaurant
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

Script şunları yapar: Python sürümünü kontrol eder → sanal ortam kurar →
bağımlılıkları yükler → `.env` dosyasını oluşturur → veritabanını hazırlar →
yönetici hesabı oluşturmanızı ister → isteğe bağlı demo veriyi yükler.

Ardından uygulamayı başlatın:

```powershell
.\run_app.bat
```

Tarayıcı otomatik olarak `http://127.0.0.1:8000` adresinde açılır.

### Elle kurulum

```powershell
cd D:\Restaurant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

> PowerShell "script çalıştırma engellendi" derse:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

Ayrıntılı adımlar ve sorun giderme: **[INSTALL_WINDOWS.md](INSTALL_WINDOWS.md)**

---

## Geliştirme kurulumu

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo          # gerçekçi demo verisi
.\run_dev.ps1                       # otomatik yeniden yükleme ile sunucu
```

Kod kalitesi ve testlerin tamamını çalıştırmak için:

```powershell
.\test_all.ps1
```

---

## Tanıtım sunumu

Programı tanıtan, iki dilli sunum seti `docs/presentation/` klasöründedir.
Dosyalar `scripts/make_presentation.py` ile **kaynaktan üretilir**; içindeki
sayılar (test, izin kodu, modül, çevrilmiş metin) `scripts/project_metrics.py`
tarafından depodan ölçülür, elle yazılmaz.

| Dosya | Ne için |
|---|---|
| `Akilli_Restaurant_Tanitim_PUBLIC.html` | Tarayıcıda sunum — ok tuşlarıyla gezinir |
| `Akilli_Restaurant_Tanitim_PUBLIC.pdf` | Ekranda/paylaşımda koyu zeminli PDF |
| `Akilli_Restaurant_Tanitim_PUBLIC.pptx` | PowerPoint'te düzenlenebilir |
| `Akilli_Restaurant_Tanitim_Baski_PUBLIC.*` | Yazdırmak için açık zeminli sürüm |
| `Smart_Restaurant_Intro_EN*_PUBLIC.*` | Aynı setin İngilizcesi |

16 slayt: çözdüğü sorun, modüller, sipariş akışı, kârlılık, istatistik,
yapay zekâ, yedekleme, yetkiler, güvenlik, kurulum, teknik temel, mali
mevzuat uyarısı ve kalite ölçütleri.

Yeniden üretmek için:

```bash
python scripts/make_presentation.py
```

İçerik `scripts/presentation_content.py` dosyasında tek yerde durur;
bir cümle değiştiğinde on dosya birden güncellenir.

---

## Uygulamayı paketleme (.exe)

Son kullanıcıya Python kurdurmadan dağıtmak için tek dosyalık bir Windows
uygulaması üretilir (PyInstaller, ~57 MB).

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

Script sırayla: ikonu üretir → **statik dosyaları üretim ayarlarıyla toplar**
→ paketi oluşturur. Sonuç `dist\Akilli Restaurant.exe` dosyasıdır.

Kalıcı klasöre kurup kısayolları oluşturmak için:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_app.ps1 -StartMenu
```

### Paketlemede dikkat edilen noktalar

| Konu | Çözüm |
|------|-------|
| Yazılabilir veri | `config/env.py` içindeki `DATA_DIR`, paketlenmiş uygulamada exe'nin yanını gösterir. Geçici açılma dizinine yazılsaydı program kapanınca tüm veri silinirdi. |
| Statik dosya manifestosu | `DEBUG=False` altında WhiteNoise hash'li dosya adları ister. `collectstatic` **üretim ayarlarıyla** çalıştırılır; `staticfiles.json` üretilmezse derleme durur. |
| Kaynak harita referansları | Küçültülmüş vendor dosyalarındaki `sourceMappingURL` yorumları `scripts/strip_sourcemaps.py` ile kaldırılmıştır; `.map` dosyaları depoda tutulmaz. |
| Konsol kod sayfası | Windows konsolu Türkçe kod sayfası (cp1254/cp857) kullanır. `launcher.py` çıktı akışlarını hataya dayanıklı hale getirir; komut çıktılarında yalnızca bu tabloda bulunan işaretler kullanılır. |
| WebSocket | Sunucu Daphne (ASGI) ile başlatılır; mutfak ekranının canlı akışı WSGI ile çalışmaz. `autobahn`'ın NVX hızlandırıcısı paketten çıkarılır (`AUTOBAHN_USE_NVX=0`). |
| Güvenlik | Paketlenmiş sürümde `IS_FROZEN` nedeniyle AI Geliştirme Merkezi ve terminal **zorla kapalıdır**; `DEBUG` kapalı çalışır. |
| Depo temizliği | `dist/`, `build/`, `Uygulama/` ve `*.exe` `.gitignore` içindedir; ikili dosyalar depoya girmez. |

---

## Docker ile kurulum

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo
```

Uygulama `http://localhost:8000` adresinde çalışır. Docker yığını PostgreSQL
ve Redis içerir; böylece çok kullanıcılı üretim benzeri bir ortam elde edilir.

> Yerel yapay zekâyı kapsayıcıdan kullanmak isterseniz `.env` içindeki
> `LMSTUDIO_BASE_URL` değerini `http://host.docker.internal:1234/v1` yapın.

---

## LM Studio kurulumu (yerel yapay zekâ)

Yerel model kullanımı **ücretsizdir, internet gerektirmez ve verileriniz
bilgisayardan çıkmaz.** Müşteri verisi içeren analizler varsayılan olarak
yalnızca yerel modele gönderilir.

1. [lmstudio.ai](https://lmstudio.ai) adresinden LM Studio'yu kurun.
2. **Discover** sekmesinden bir model indirin. Test edilmiş seçenekler:

   | Model | Rol | Not |
   |---|---|---|
   | `google/gemma-4-12b-qat` | Genel asistan, belge analizi | Muhakemeli; token bütçesi yüksek olmalı |
   | `qwen/qwen3-vl-8b` | Muhakeme, kod, raporlama | Hızlı, dengeli |
   | `qwen2.5-math-7b-instruct` | Maliyet ve sayısal analiz | — |
   | `moondream-2b` | Fiş / ürün görseli analizi | Hafif görsel model |
   | `biomistral-7b` | Alerjen bilgisi (yardımcı) | Tıbbi tavsiye değildir |
   | `text-embedding-nomic-embed-text-v1.5` | Vektör gömme | Arama/RAG için |

3. **Developer** sekmesine geçin ve **Start Server** düğmesine basın.
   Sunucu varsayılan olarak `http://127.0.0.1:1234` adresinde çalışır.
4. Bağlantıyı doğrulayın:

   ```powershell
   python manage.py ai_check --provider lmstudio --ask "Merhaba, çalışıyor musun?"
   ```

   Bu komut model listesini çeker, görev→model eşlemesini **gerçek sunucu
   yanıtıyla karşılaştırır** ve bir test sorusu gönderir.

5. Uygulama içinden: **Yapay Zekâ → Sağlayıcılar → Test et**

> **Muhakeme (reasoning) modelleri hakkında:** `gemma-4-12b-qat` gibi modeller
> yanıt üretmeden önce token harcayarak "düşünür". Token sınırı düşükse yanıt
> boş döner. Bu yüzden varsayılan `AI_MAX_TOKENS=2500`'dür; düşürmeyin.
> Sistem bu durumu algılar ve size ne yapmanız gerektiğini açıkça söyler.

LM Studio kapalıysa uygulama **hata vermez** — yapay zekâ özellikleri
"kullanılamıyor" uyarısı gösterir, geri kalan her şey normal çalışır.

---

## NVIDIA NIM kurulumu (bulut yapay zekâ)

1. [build.nvidia.com](https://build.nvidia.com) adresinde oturum açın.
2. Bir model sayfasına gidin ve **Generate API Key** ile anahtar oluşturun
   (`nvapi-` ile başlar).
3. Anahtarı **yalnızca `.env` dosyasına** yazın:

   ```env
   NVIDIA_ENABLED=True
   NVIDIA_API_KEY=nvapi-...
   ```

4. Uygulamayı yeniden başlatın ve test edin:

   ```powershell
   python manage.py ai_check --provider nvidia
   ```

Katalogdan doğrulanmış varsayılan model eşlemesi (hepsi **Free Endpoint**):

| Görev | Model | Bağlam |
|---|---|---|
| Genel | `nvidia/nemotron-3.5-lightning-30b-a3b` | 1M |
| Muhakeme / rapor | `nvidia/nemotron-3-ultra-550b-a55b` | 1M |
| Kod | `zai/glm-5.2` | — |
| Görsel / fiş okuma | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 262K |
| Gömme (embedding) | `nvidia/nemotron-3-embed-1b` | — |

> **Maliyet uyarısı:** "Free Endpoint" modelleri ücretsiz kota ile gelir; kota
> dolduğunda veya ücretli/partner uç noktaya geçtiğinizde **ücretlendirme
> başlayabilir.** Bu yüzden sistemde günlük/aylık USD bütçe sınırı vardır
> (`AI_DAILY_BUDGET_USD`, `AI_MONTHLY_BUDGET_USD`). Bütçe dolduğunda sistem
> bulut çağrılarını durdurur ve otomatik olarak yerel modele düşer.

**Diğer desteklenen sağlayıcılar:** OpenAI uyumlu API, Anthropic, Google
Gemini, OpenRouter, Ollama. Hepsi isteğe bağlıdır ve aynı arayüzden yönetilir.
Ayrıntılar: **[AI_INTEGRATION.md](AI_INTEGRATION.md)**

---

## Yönetici hesabı oluşturma

```powershell
python manage.py createsuperuser
```

Kullanıcı adı, e-posta ve parola sorulur. Oluşturulan hesap otomatik olarak
**İşletme sahibi** rolünü ve tüm izinleri alır.

POS terminalinde hızlı kullanıcı değişimi ve yetkili onayı için bir de PIN
tanımlayın: uygulamada **Profil → PIN kodu**.

Yeni personel hesapları arayüzden açılır: **Ayarlar → Kullanıcılar → Yeni
kullanıcı**. Rol seçtiğinizde ilgili izinler otomatik atanır.

---

## Demo veri ve giriş bilgileri

```powershell
python manage.py seed_demo            # 30 günlük gerçekçi geçmiş
python manage.py seed_demo --days 90  # daha uzun geçmiş
python manage.py seed_demo --reset    # önce temizle
```

Oluşturulanlar: 25 ürün ve reçeteleri, 32 malzeme, 30 masa, 60 müşteri,
14 personel, ~550 tamamlanmış sipariş, 70 yorum, rezervasyonlar, giderler.

| Kullanıcı | Rol |
|---|---|
| `patron` | İşletme sahibi (tüm yetkiler) |
| `gmudur` | Genel müdür |
| `mudur` | Restoran müdürü |
| `sef` | Şef |
| `sefgarson` | Şef garson |
| `garson1` | Garson |
| `kasiyer` | Kasiyer |
| `barmen` | Bar personeli |
| `depocu` | Depo / satın alma |
| `muhasebe` | Muhasebe |
| `kurye1` | Kurye |

**Parola sabit değildir.** `seed_demo` her çalıştırmada rastgele güçlü bir
parola üretir ve komut çıktısında **bir kez** gösterir; kendi parolanızı
vermek isterseniz `--password` kullanın. POS yetkili onayı için üretilen
PIN kodları da aynı çıktıda bir kez listelenir.

> ⚠️ Demo hesapları yalnızca deneme içindir. **Gerçek kullanımdan önce
> `--reset` ile temizleyin veya parolaları değiştirin.**

Farklı rollerle giriş yaparak yetkilendirmenin nasıl çalıştığını görebilirsiniz:
garson kullanıcısı iptal edemez, kasiyer menüyü değiştiremez, şef kullanıcı
yönetimine giremez.

---

## Test komutları

```powershell
# Tüm testler
python -m pytest

# Kapsam raporu ile
python -m pytest --cov=apps --cov-report=term-missing

# Yalnızca belirli bir alan
python -m pytest tests/test_orders.py -v
python -m pytest tests/test_security.py -v

# Kod kalitesi
python -m ruff check .
python -m black --check .
python -m mypy apps

# Güvenlik
python -m bandit -c pyproject.toml -r apps config
python -m pip_audit

# Hepsi birden
.\test_all.ps1
```

Güncel sonuçlar: **[TEST_REPORT.md](TEST_REPORT.md)**

---

## Güvenlik notları

- **Gizli değerler `.env` dosyasındadır** ve `.gitignore` ile korunur. API
  anahtarları veritabanına yazılmaz, arayüzde maskeli gösterilir, günlüklerde
  otomatik olarak temizlenir.
- **Rol tabanlı erişim** her görünüm, her API uç noktası ve her menü öğesi için
  ayrı ayrı uygulanır.
- **Denetim kaydı** değiştirilemez; iptal, iade, indirim, yetki değişikliği,
  dışa aktarma, AI çağrısı ve terminal komutları kayıt altına alınır.
- **Brute-force koruması**: 5 başarısız denemede hesap+IP 1 saat kilitlenir.
- **Güvenli terminal** yalnızca izin listesindeki komutları çalıştırır; silme,
  biçimlendirme, ağ indirme, komut zincirleme ve proje dışına erişim engellidir.
- **AI kod önerileri** siz diff'i görüp onaylamadan uygulanmaz; uygulama
  öncesinde geri alma noktası oluşturulur ve ayrı Git dalı açılır.
- **KVKK**: müşteri kişisel verileri yetkisiz kullanıcılara maskeli gösterilir,
  yapay zekâya gönderilmeden önce otomatik maskelenir, silme talebinde geri
  döndürülemez şekilde anonimleştirilir (sipariş geçmişi korunur).

Üretime almadan önce mutlaka okuyun: **[SECURITY.md](SECURITY.md)**

### ⚖️ Mali mevzuat uyarısı

Bu sistemin ürettiği fiş, adisyon ve "gün sonu raporu" belgeleri **işletme içi
bilgilendirme amaçlıdır ve yasal mali belge yerine geçmez.** Türkiye'de yasal
Z raporu onaylı ödeme kaydedici cihaz (ÖKC / yeni nesil yazarkasa) tarafından,
e-Fatura ve e-Arşiv ise yetkili bir özel entegratör üzerinden üretilmelidir.
Sistem bu entegrasyonlar için arayüz hazırlığı içerir; **gerçek mali belge
ürettiği iddia edilmez.**

---

## Belgeler

| Belge | İçerik |
|---|---|
| [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md) | Adım adım Windows kurulumu ve sorun giderme |
| [USER_GUIDE.md](USER_GUIDE.md) | Günlük kullanım: POS, mutfak, stok, rezervasyon |
| [ADMIN_GUIDE.md](ADMIN_GUIDE.md) | Yönetici: roller, ayarlar, yedekleme/geri yükleme, istatistik merkezi, kasa |
| [AI_INTEGRATION.md](AI_INTEGRATION.md) | Yapay zekâ mimarisi, sağlayıcılar, maliyet |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Teknik mimari, veri modeli, tasarım kararları |
| [SECURITY.md](SECURITY.md) | Güvenlik modeli ve üretim kontrol listesi |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | İncelenen projeler ve lisanslar |
| [TEST_REPORT.md](TEST_REPORT.md) | Test sonuçları ve kapsam |
| [PACKAGING_TEST.md](PACKAGING_TEST.md) | Paketlenmiş uygulamanın (.exe) uçtan uca doğrulaması |
| [CHANGELOG.md](CHANGELOG.md) | Sürüm geçmişi |
| [ROADMAP.md](ROADMAP.md) | Planlanan geliştirmeler |

---

## Teknoloji yığını

**Arka uç:** Python 3.11+ · Django 5.2 · Django REST Framework · Django
Channels (WebSocket) · SQLite / PostgreSQL

**Ön uç:** Bootstrap 5 · HTMX · Alpine.js · Chart.js — hepsi **yerel olarak
paketlenmiştir**, CDN gerektirmez, internet olmadan çalışır.

**Raporlama:** ReportLab (PDF) · openpyxl (Excel)

**Yapay zekâ:** LM Studio · Ollama · NVIDIA NIM · OpenAI uyumlu · Anthropic ·
Google Gemini · OpenRouter

**Kalite:** pytest · ruff · black · mypy · bandit · pip-audit

---

## Katkı

Sorun bildirimi ve katkılar memnuniyetle karşılanır. Katkı göndermeden önce:

```powershell
.\test_all.ps1
```

komutunun hatasız tamamlandığından emin olun.

---

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE).

Bu proje **sıfırdan yazılmıştır.** Geliştirme sürecinde incelenen açık kaynak
projeler, lisansları ve hangi fikirlerden esinlenildiği
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dosyasında açıkça belirtilmiştir.
