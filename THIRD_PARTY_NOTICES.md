# Üçüncü Taraf Bildirimleri ve Lisans Beyanı

Bu belge, **Akıllı Restaurant Yönetim Sistemi**'nin geliştirilmesi sırasında
incelenen açık kaynak projeleri, bu projelerin lisanslarını, hangi fikirlerden
esinlenildiğini ve **kod alınıp alınmadığını** şeffaf biçimde açıklar.

---

## 1. Özet beyan

> **Bu projenin kaynak kodu sıfırdan yazılmıştır.**
> Aşağıda listelenen projelerden **hiçbir kaynak kodu, şablon, stil dosyası
> veya veritabanı şeması kopyalanmamış ya da uyarlanmamıştır.** İnceleme
> yalnızca *özellik kapsamı* ve *mimari yaklaşım* karşılaştırması amacıyla,
> GitHub üzerinde herkese açık depo meta verileri ve dosya ağaçları üzerinden
> yapılmıştır.

Bu nedenle bu projede korunması gereken **üçüncü taraf telif bildirimi
bulunmamaktadır**. Yine de şeffaflık ilkesi gereği incelenen tüm kaynaklar
lisanslarıyla birlikte aşağıda listelenmiştir.

---

## 2. İncelenen açık kaynak projeler

Lisans bilgileri **GitHub API üzerinden doğrulanmıştır** (kontrol tarihi:
15 Ağustos 2026). Hiçbiri GPL/AGPL değildir; tamamı MIT lisanslıdır.

| Proje | Lisans (doğrulandı) | Yıldız | Dil | Son güncelleme |
|---|---|---|---|---|
| [betofleitass/django_point_of_sale](https://github.com/betofleitass/django_point_of_sale) | MIT | 113 | HTML/Python | 2025-12-08 |
| [TheSaMNaN/Restaurant-Billing-System](https://github.com/TheSaMNaN/Restaurant-Billing-System) | MIT | 8 | HTML/Python | 2025-08-25 |
| [iamdelowershuvo/Eieat-Marketplace-Django](https://github.com/iamdelowershuvo/Eieat-Marketplace-Django) | MIT | 0 | JavaScript/Python | 2025-10-26 |
| [rajshah16/food-ordering-system-with-ML](https://github.com/rajshah16/food-ordering-system-with-ML) | MIT | 3 | JavaScript/Python | 2021-04-05 |
| [s-rigaud/Restaurant-Management-System](https://github.com/s-rigaud/Restaurant-Management-System) | MIT | 0 | Python | 2020-02-07 |

### Neyden esinlenildi, neyden esinlenilmedi

| Proje | İncelenen yön | Bu projeye etkisi |
|---|---|---|
| `django_point_of_sale` | Django uygulama ayrımı (`pos`, `products`, `sales`, `customers`) | **Fikir düzeyinde:** modülleri iş alanına göre ayırma yaklaşımı doğrulandı. Bu projede çok daha ayrıntılı bir ayrım kullanıldı (12 uygulama) ve iş mantığı `services.py` katmanına taşındı — kaynak projede bu katman yoktur. **Kod alınmadı.** |
| `Restaurant-Billing-System` | Tek uygulamalı adisyon/fatura akışı | **Karşıt örnek olarak değerlendirildi:** tek `restaurant` uygulaması ölçeklenmediği için bu projede modüler yapı tercih edildi. **Kod alınmadı.** |
| `Eieat-Marketplace-Django` | Çok satıcılı pazaryeri ve sipariş akışı | Kapsam farklı (pazaryeri ≠ tek restoran yönetimi). Yalnızca sipariş durum makinesi karşılaştırması yapıldı. **Kod alınmadı.** |
| `food-ordering-system-with-ML` | Makine öğrenmesiyle ürün önerisi | **Yaklaşım reddedildi:** proje 2021'den beri güncellenmemiş ve eğitilmiş model dosyalarına bağımlı. Bu projede bunun yerine deterministik istatistik + LLM yorumlaması tercih edildi. **Kod alınmadı.** |
| `Restaurant-Management-System` | Küçük ölçekli yönetim aracı (16 dosya) | Kapsam çok dar. **Kod alınmadı.** |

### İncelenen projelerde bulunmayan, bu projede sıfırdan geliştirilen özellikler

Karşılaştırma sonucunda, incelenen beş projenin **hiçbirinde** bulunmayan
şu yetenekler bu projede özgün olarak tasarlanıp yazılmıştır:

- Reçete (BOM) tabanlı **otomatik stok düşümü** ve fire oranı hesabı
- **Parti (lot) bazlı FIFO/FEFO** tüketimi ve son kullanma tarihi takibi
- WebSocket tabanlı **mutfak ekranı (KDS)** ve istasyona göre KOT ayrımı
- **12 rollü, 60+ izinli** işlev bazlı yetkilendirme ve yetkili PIN onayı
- Çok sağlayıcılı **yapay zekâ ağ geçidi** (yönlendirme, yedekleme, devre
  kesici, bütçe kontrolü, KVKK maskeleme)
- **AI Geliştirme Merkezi** ve allowlist tabanlı güvenli terminal
- Menü mühendisliği, talep tahmini, anormallik tespiti gibi **akıllı analizler**
- Değiştirilemez **denetim kaydı** ve KVKK anonimleştirme altyapısı
- Hesap bölme (eşit / koltuk / ürün bazlı), adisyon birleştirme, masa taşıma

---

## 3. Kullanılan üçüncü taraf yazılım bağımlılıkları

Aşağıdaki paketler `requirements.txt` ile **PyPI üzerinden kurulur**; kaynak
kodları bu depoya dahil edilmemiştir. Her biri izin verici (permissive) lisansa
sahiptir; hiçbiri GPL/AGPL değildir.

### Python paketleri

| Paket | Lisans | Kullanım amacı |
|---|---|---|
| Django | BSD-3-Clause | Web çatısı |
| Django REST Framework | BSD-3-Clause | REST API |
| django-filter | BSD-3-Clause | API filtreleme |
| django-cors-headers | MIT | CORS yönetimi |
| djangorestframework-simplejwt | MIT | JWT kimlik doğrulama |
| Channels | BSD-3-Clause | WebSocket desteği |
| Daphne | BSD-3-Clause | ASGI sunucusu |
| Twisted | MIT | Daphne bağımlılığı |
| django-axes | MIT | Brute-force koruması |
| WhiteNoise | MIT | Statik dosya sunumu |
| python-dotenv | BSD-3-Clause | Ortam değişkeni yükleme |
| cryptography | Apache-2.0 / BSD-3-Clause | Şifreleme yardımcıları |
| pyOpenSSL | Apache-2.0 | TLS desteği |
| Pillow | MIT-CMU | Görsel işleme |
| qrcode | BSD-3-Clause | QR menü kodu üretimi |
| openpyxl | MIT | Excel dışa aktarma |
| ReportLab | BSD-3-Clause | PDF üretimi |
| httpx | BSD-3-Clause | AI sağlayıcı HTTP istemcisi |

### Geliştirme bağımlılıkları

| Paket | Lisans | Kullanım amacı |
|---|---|---|
| pytest, pytest-django, pytest-cov | MIT | Test altyapısı |
| ruff | MIT | Linter |
| black | MIT | Kod biçimlendirici |
| mypy, django-stubs | MIT | Tip denetimi |
| bandit | Apache-2.0 | Güvenlik taraması |
| pip-audit | Apache-2.0 | Bağımlılık açığı taraması |

### İsteğe bağlı bağımlılıklar

| Paket | Lisans | Kullanım amacı |
|---|---|---|
| psycopg | LGPL-3.0 | PostgreSQL sürücüsü — **yalnızca kütüphane olarak kullanılır, kodu bu projeye dahil edilmez.** LGPL dinamik bağlantıya izin verir. |
| Celery, redis, django-celery-beat | BSD-3-Clause | Arka plan görevleri |
| channels-redis | BSD-3-Clause | Çok sunuculu WebSocket |
| pandas | BSD-3-Clause | Gelişmiş veri analizi |
| Playwright | Apache-2.0 | Uçtan uca UI testleri |

---

## 4. Ön yüz varlıkları

Aşağıdaki dosyalar `static/vendor/` klasöründe **yerel olarak paketlenmiştir**
(internet olmadan çalışabilmesi için). Her biri kendi lisansı altında dağıtılır
ve lisans metinleri paketlerin içinde korunmuştur.

| Varlık | Sürüm | Lisans | Kaynak |
|---|---|---|---|
| Bootstrap (CSS + JS) | 5.3.3 | MIT | getbootstrap.com |
| Bootstrap Icons (font + CSS) | 1.11.3 | MIT | icons.getbootstrap.com |
| HTMX | 1.9.12 | BSD-2-Clause | htmx.org |
| Alpine.js | 3.14.8 | MIT | alpinejs.dev |
| Chart.js | 4.4.7 | MIT | chartjs.org |

**Yapılan tek değişiklik:** Bu dosyaların sonundaki `sourceMappingURL`
yorum satırları kaldırılmıştır (`scripts/strip_sourcemaps.py`). Bu yorumlar
yalnızca tarayıcı geliştirici araçlarının `.map` dosyalarını bulması içindir;
`.map` dosyalarını dağıtmadığımız için referans geçersizdir ve Django'nun
statik dosya toplama adımını hataya düşürür. **Kodun kendisine, telif ve
lisans başlıklarına dokunulmamıştır.**

**Yazı tipi:** Arayüz, işletim sisteminin kendi sistem yazı tipini kullanır
(`Segoe UI`, `system-ui`). Harici yazı tipi **indirilmez veya dağıtılmaz**;
bu nedenle ek bir font lisansı gerekmez.

**İkonlar:** Yalnızca Bootstrap Icons (MIT) kullanılır. Başka ikon seti
dahil edilmemiştir.

**Görseller:** Depoda telif korumalı fotoğraf, logo veya grafik
**bulunmamaktadır.** Ürün görseli alanları boştur; kullanıcı kendi
görsellerini yükler.

---

## 5. Demo verisi

`python manage.py seed_demo` komutuyla üretilen tüm veriler **program
tarafından üretilmiş kurgusal verilerdir**:

- Müşteri adları yaygın Türkçe ad-soyad listelerinden rastgele birleştirilir.
- Telefon numaraları rastgele üretilir ve gerçek abonelere ait değildir.
- E-posta adresleri `@ornek.com` gibi ayrılmış örnek alan adları kullanır.
- Ürün, tedarikçi ve firma adları kurgusaldır.
- Yorum metinleri bu proje için yazılmıştır; hiçbir gerçek platformdan
  alınmamıştır.

**Depoda hiçbir gerçek kişiye ait veri bulunmamaktadır.**

---

## 6. Yapay zekâ modelleri

Bu proje **hiçbir yapay zekâ modelini dağıtmaz veya içermez.** Modeller
kullanıcının kendi ortamında çalışır veya kullanıcının kendi API anahtarıyla
uzak bir sağlayıcıdan çağrılır.

| Sağlayıcı | Model lisansı | Not |
|---|---|---|
| LM Studio (yerel) | Kullanıcının indirdiği modele bağlı | Model lisansını kullanıcı kontrol eder |
| Ollama (yerel) | Kullanıcının indirdiği modele bağlı | — |
| NVIDIA NIM | NVIDIA API kullanım koşulları | Kullanıcının kendi anahtarı |
| OpenAI / Anthropic / Google / OpenRouter | İlgili sağlayıcının koşulları | Kullanıcının kendi anahtarı |

Bu projedeki tüm **istemler (prompt)** özgün olarak yazılmıştır.

---

## 7. Lisans uyumluluk kontrolü

| Kontrol | Sonuç |
|---|---|
| GPL/AGPL lisanslı kod dahil edildi mi? | ❌ Hayır |
| Lisansı belirtilmemiş depodan kod alındı mı? | ❌ Hayır |
| Üçüncü taraf kaynak kodu depoya kopyalandı mı? | ❌ Hayır |
| Ön yüz varlıklarının lisansları izin verici mi? | ✅ Evet (MIT / BSD-2) |
| Telif korumalı görsel/font dağıtılıyor mu? | ❌ Hayır |
| Depoda gerçek kişisel veri var mı? | ❌ Hayır |
| Depoda API anahtarı / gizli değer var mı? | ❌ Hayır (`.gitignore` + secret taraması) |

---

## 7.1 Belge üretiminde kullanılan yazı tipi

Tanıtım sunumunun PDF çıktısı (`docs/presentation/*_PUBLIC.pdf`) yazı tipini
**gömer**; bu yüzden yazı tipi lisansı dağıtım lisansıdır ve burada açıkça
belirtilir.

| Yazı tipi | Lisans | Nereden gelir | Not |
|---|---|---|---|
| **DejaVu Sans** | DejaVu Fonts License (Bitstream Vera türevi; izin verici, gömmeye ve yeniden dağıtıma açık) | Sistemde varsa birinci tercih | Türkçe harfleri (ş ğ ı İ) tam kapsar |
| **Bitstream Vera Sans** | Bitstream Vera Fonts Copyright (izin verici, gömmeye ve yeniden dağıtıma açık) | ReportLab paketiyle birlikte gelir | Varsayılan; ek indirme gerekmez |

`scripts/make_presentation.py` bu sırayı izler ve **tescilli bir sistem yazı
tipine düşmek zorunda kalırsa çıktıya uyarı yazar** — o durumda PDF
dağıtılmadan önce yazı tipi lisansı doğrulanmalıdır. Yazı tipinde bulunmayan
işaretler (₺, ↔, →) okunur karşılıklarıyla değiştirilir; sessizce boş
bırakılmaz.

Depoda gömülü bir yazı tipi dosyası **bulunmaz**; ikisi de kurulu
ortamdan/bağımlılıktan gelir.

---

## 7.2 Ön yüz varlıkları (yerel olarak paketlenir)

| Bileşen | Lisans | Yol |
|---|---|---|
| Bootstrap 5 | MIT | `static/vendor/css/bootstrap.min.css`, `static/vendor/js/bootstrap.bundle.min.js` |
| Bootstrap Icons | MIT | `static/vendor/css/bootstrap-icons.min.css` + `fonts/` |
| Alpine.js | MIT | `static/vendor/js/alpine.min.js` |
| htmx | BSD-2-Clause | `static/vendor/js/htmx.min.js` |
| Chart.js | MIT | `static/vendor/js/chart.umd.min.js` |

Bu varlıklar bilinçli olarak depoda tutulur: harici bir CDN'e istek
yapılmaması, hem gizlilik (üçüncü tarafa istek gitmez) hem de güvenlik
(içerik güvenlik politikası `default-src 'self'` ile sıkı kalabilir) gereğidir.

---

## 7.3 Makine-okunur yazılım listesi (SBOM)

Çalışma zamanı bağımlılıklarının tam listesi ve sürümleri iki biçimde
üretilir:

- `sbom.spdx.json` (SPDX 2.3)
- `sbom.cdx.json` (CycloneDX)

Her ikisi de depodaki bildirilen bağımlılıklardan üretilir; yayın öncesi
yeniden üretilmelidir.

---

## 8. Bildirim

Bu belgede bir hata olduğunu veya bir lisans ihlali bulunduğunu
düşünüyorsanız lütfen depoda bir **issue** açın. Bildirim en kısa sürede
incelenip düzeltilecektir.

---

*Son güncelleme: 19 Ağustos 2026*
