# Güvenlik Modeli ve Üretime Alma Kontrol Listesi

Bu belge **işletmeciler ve geliştiriciler** içindir: uygulanan güvenlik
denetimlerini ve sistemi gerçek kullanıma almadan önce yapılması gerekenleri
anlatır.

Güvenlik açığı bildirimi bu belgede DEĞİLDİR; sorumlu açıklama süreci için
depo kökündeki [`SECURITY.md`](../SECURITY.md) dosyasına bakın.

---

## 2. Kimlik doğrulama ve oturum

| Önlem | Ayrıntı |
|---|---|
| Giriş | Kullanıcı adı **veya** e-posta ile |
| Zamanlama saldırısı | Kullanıcı bulunamasa bile parola hash'lemesi çalıştırılır |
| Brute force | 5 başarısız denemede kullanıcı + IP 1 saat kilitlenir (django-axes) |
| Parola politikası | En az 10 karakter · 4 karakter sınıfından en az 3'ü · aynı karakter 4+ kez tekrarlanamaz · yaygın parola listesi kontrolü |
| Oturum | HttpOnly · SameSite=Lax · varsayılan 8 saat · her istekte yenilenir |
| İlk giriş | `must_change_password` ile parola değiştirmeye zorlanabilir |
| POS PIN | 4-8 hane, **hash'lenerek** saklanır; tekrar (1111), ardışık (1234) ve yaygın PIN'ler reddedilir |
| PIN ile kullanıcı değişimi | Yalnızca **oturum açılmış** bir terminalde; 5 hatalı denemede kullanıcı ve IP 15 dakika kilitlenir |
| İlk/geçici parola | `must_change_password` işaretli hesap, parola değiştirilene kadar **hiçbir** korumalı sayfayı açamaz (ara katman) |
| Varsayılan hesap | **Yoktur.** Ürün hazır kimlik bilgisiyle gelmez |

Tüm giriş, başarısız giriş ve çıkış olayları denetim kaydına yazılır.

---

## 3. Yetkilendirme

60+ işlev bazlı izin kodu ve 12 rol. Değerlendirme sırası:

1. Süper kullanıcı → tüm izinler
2. `denied_permissions` → **kesin ret** (rolde olsa bile)
3. `extra_permissions` → kesin izin
4. Rol matrisi → varsayılan

Uygulama noktaları:

- **Görünümler:** `@require_permission("pos.void")`
- **Sınıf tabanlı görünümler:** `PermissionRequiredMixin`
- **REST API:** `HasPermissionCode` + `required_permissions`
- **Menü:** yetkisi olmayan kullanıcıya menü öğesi gösterilmez
- **Şablon:** hassas alanlar izne göre gizlenir/maskelenir

### Yetkili onayı

İptal, iade, indirim, fiyat değiştirme ve adisyon yeniden açma işlemleri
`MANAGER_APPROVAL_PERMISSIONS` kümesindedir. Yetkisi olmayan bir kullanıcı bu
işlemi başlatırsa **yetkili bir kullanıcının kullanıcı adı + PIN'i** istenir.
Başarılı ve başarısız onay denemeleri kayda geçer.

---

## 4. Veri koruma (KVKK)

| Önlem | Uygulama |
|---|---|
| Maskeleme | `customer.pii` izni olmayan kullanıcıya telefon/e-posta maskeli gösterilir |
| Rıza kaydı | Her izin türü için zaman damgalı `ConsentRecord` |
| AI maskeleme | E-posta, telefon, T.C. kimlik, kart no ve IBAN istemden temizlenir |
| Hassas görev | Müşteri verisi içeren AI çağrıları yalnızca **yerel modele** gider |
| Günlük | Uygulama günlüklerinde PII ve gizli anahtarlar otomatik maskelenir |
| Silme hakkı | `Customer.anonymize()` kişisel verileri geri döndürülemez şekilde temizler |

### Anonimleştirme davranışı

Silme talebinde ad, telefon, e-posta, adres, doğum tarihi, tercihler ve
alerji notları silinir; rıza kayıtları kaldırılır. **Sipariş geçmişi silinmez** —
anonim bir kayda bağlanır. Bu, mali kayıt bütünlüğünü korurken kişiyi
tanımlanamaz hâle getirir. İşlem `data.erase` izni gerektirir ve kritik
seviyede denetim kaydı bırakır.

---

## 5. Uygulama güvenliği

| Tehdit | Önlem |
|---|---|
| SQL injection | Yalnızca Django ORM; ham SQL kullanılmaz |
| XSS | Django şablon otomatik kaçışı + sıkı CSP |
| CSRF | Django yerleşik koruma; `apiPost` token'ı hem başlıkta hem gövdede gönderir |
| Clickjacking | `X-Frame-Options: DENY` + `frame-ancestors 'none'` |
| MIME sniffing | `X-Content-Type-Options: nosniff` |
| Açık yönlendirme | Yalnızca adlandırılmış URL'lere yönlendirme |
| Kütle atama | ModelForm'larda açık `fields` listesi |
| Hız sınırlama | Yol bazlı `RateLimitMiddleware` + DRF throttling |

### İçerik Güvenlik Politikası

```
default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval';
style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;
font-src 'self' data:; connect-src 'self' ws: wss:;
frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```

> `'unsafe-inline'` ve `'unsafe-eval'`, Alpine.js'in çalışması için gereklidir.
> Tüm varlıklar yerel paketlendiği için `default-src 'self'` sıkı tutulabilir;
> harici bir kaynağa istek yapılamaz.

### Dosya yükleme

Üç katmanlı doğrulama:

1. **Uzantı** — yalnızca `.jpg .jpeg .png .webp .gif .pdf .csv .xlsx`
2. **Boyut** — en fazla 10 MB
3. **Magic byte** — dosyanın gerçek imzası kontrol edilir, böylece `.jpg`
   adıyla yüklenen çalıştırılabilir dosya reddedilir

Ayrıca yol geçişi (`/`, `\`, `..`) içeren dosya adları reddedilir.

---

## 6. Gizli değer yönetimi

| Kural | Uygulama |
|---|---|
| Depolama | Yalnızca `.env` — **veritabanına asla yazılmaz** |
| Sürüm kontrolü | `.env` ve türevleri `.gitignore` içinde; yalnızca `.env.example` yüklenir |
| Görüntüleme | Arayüzde maskeli (`nvap••••••••••••1f`) |
| Günlükler | `SensitiveDataFilter` ile otomatik temizlenir |
| Alt süreçler | Terminal komutlarına `*API_KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*` içeren değişkenler **aktarılmaz** |
| API yanıtları | Anahtar hiçbir uç noktadan dönmez (test ile doğrulanır) |

Tanınan anahtar biçimleri: `nvapi-`, `sk-`, `sk-proj-`, `sk-ant-`, `sk-or-v1-`,
`AIza`, `ghp_/gho_/ghu_/ghs_/ghr_`, `AKIA`, JWT ve genel `key=değer` kalıpları.

---

## 7. Güvenli terminal ve AI Geliştirme Merkezi

Bu bölüm kod çalıştırabildiği için en yüksek risk alanıdır. Altı katmanlı
savunma uygulanır:

### 7.1 Allowlist (deny-by-default)

Yalnızca şu programlar çalıştırılabilir:
`python · py · pytest · ruff · black · mypy · bandit · pip · npm · npx · git · docker`

`pip`, `npm`, `git` ve `docker` için ayrıca **alt komut listesi** vardır.
Listede olmayan her komut reddedilir.

### 7.2 Kabuk yok

`subprocess.run(..., shell=False)` ile çalışır. `&&`, `||`, `|`, `;`, backtick
ve `$( )` yorumlanmaz — komut zinciri kurulamaz. Bu kalıplar ayrıca desen
kontrolünde de reddedilir.

### 7.3 Yol hapsi

Çalışma dizini `DEVCENTER_ROOT` ile sınırlıdır. Argümanlardaki `..` ve kök
dışındaki mutlak yollar reddedilir.

### 7.4 Yasak kalıplar

```
rm · rmdir · del · Remove-Item · format · diskpart · mkfs
reg add/delete · Set-ItemProperty · HKLM · HKCU
net user · Add-LocalUser · useradd · passwd
shutdown · taskkill · Stop-Process · kill -9
curl · wget · Invoke-WebRequest
cat · type · Get-Content   (dosya okuma için kod görüntüleyici kullanılır)
.env · id_rsa · .ssh · credential · password · secret · token
git push · git reset --hard · git clean -f
manage.py flush/sqlflush/dbshell
DROP TABLE · TRUNCATE · DELETE FROM
> · >> · <   (çıktı yönlendirme)
```

### 7.5 Onay kapısı

Yan etkili komutlar kullanıcı onayı olmadan çalışmaz:
`pip install` · `npm install` · `npm ci` · `git add` · `git commit` ·
`git checkout` · `git switch` · `git restore` · `git stash` ·
`docker compose` · `manage.py migrate` · `makemigrations` · `flush` · `loaddata`

### 7.6 Kod önerisi koruması

| Aşama | Koruma |
|---|---|
| Dosya seçimi | `.env`, veritabanı, `.git`, `.venv`, `media`, `backups`, `logs` **korumalı** |
| Uzantı | Yalnızca `.py .html .css .js .md .txt .json .yml .yaml` |
| Önizleme | Değişiklik **her zaman diff olarak** gösterilir |
| Onay | Kullanıcı onaylamadan hiçbir dosya yazılmaz |
| Yedek | Uygulamadan önce otomatik geri alma noktası |
| Dal | Değişiklik ayrı Git dalına uygulanır, ana dala değil |
| Test | Testler çalıştırılmışsa ve **başarısızsa uygulama reddedilir** |
| Hata | Yazma sırasında hata olursa yedekten otomatik geri yükleme |
| Kayıt | Uygulama kritik seviyede denetim kaydı bırakır |

### 7.7 Üretimde kapalı

`DEVCENTER_ENABLED` ve `DEVCENTER_TERMINAL_ENABLED` üretim ortamında
varsayılan olarak **kapalıdır**. Açmak için `.env` içinde açıkça
etkinleştirilmeleri gerekir.

> **Tavsiye:** Üretim sunucusunda bu iki değeri `False` bırakın. Geliştirme
> merkezini yalnızca geliştirme/test makinesinde kullanın.

---

## 8. Denetim kaydı

Kaydedilen olaylar: giriş · başarısız giriş · çıkış · oluşturma · güncelleme ·
silme · **iptal** · **iade** · **indirim** · yetki değişikliği · dışa aktarma ·
**AI çağrısı** · **terminal komutu** · **kod uygulama** · kasa işlemi ·
KVKK veri silme.

Her kayıt: zaman · kullanıcı (+ silinse bile kullanıcı adı anlık görüntüsü) ·
işlem · önem düzeyi · nesne · açıklama · değişiklikler · IP · tarayıcı.

Kayıtlar **değiştirilemez** — mevcut bir kaydı güncelleme denemesi hata verir.

Görüntüleme: `audit.view` izni · **Ayarlar → Denetim kayıtları**

---

## 9. Üretim kontrol listesi

Sistemi gerçek kullanıma almadan önce **tamamını** uygulayın:

### Zorunlu

- [ ] `.env` içinde `DJANGO_ENV=production` ve `DJANGO_DEBUG=False`
- [ ] Güçlü, benzersiz `DJANGO_SECRET_KEY` üretin:
      `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`
- [ ] `DJANGO_ALLOWED_HOSTS` yalnızca gerçek alan adınızı içersin
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` `https://` ile başlasın
- [ ] HTTPS kurun ve `SECURE_SSL_REDIRECT=True`,
      `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True` yapın
- [ ] `DEVCENTER_ENABLED=False` ve `DEVCENTER_TERMINAL_ENABLED=False`
- [ ] **Demo hesaplarını silin** veya parolalarını değiştirin
      (`python manage.py seed_demo --reset`)
- [ ] Tüm kullanıcılara güçlü parola ve PIN tanımlayın
- [ ] PostgreSQL'e geçin (çok terminalli kullanımda)
- [ ] Otomatik yedekleme kurun (`backup.ps1` + zamanlanmış görev)

### Önerilen

- [ ] `AI_DAILY_BUDGET_USD` ve `AI_MONTHLY_BUDGET_USD` değerlerini belirleyin
- [ ] `AI_MASK_PII=True` ve `AI_SENSITIVE_LOCAL_ONLY=True` bırakın
- [ ] Redis kurup `CHANNEL_LAYER=redis` yapın (çok sunuculu dağıtım)
- [ ] Ters vekil sunucu (nginx / IIS) arkasına alın
- [ ] `logs/` klasörünü izleyin veya merkezî günlük sistemine gönderin
- [ ] Bağımlılıkları düzenli tarayın: `python -m pip_audit`
- [ ] Yedeklerin **geri yüklenebildiğini** test edin

### Doğrulama

```powershell
python manage.py check --deploy
```

Üretim yapılandırmasında bu komut **hiçbir uyarı vermemelidir.**
Geliştirme ortamında 5 uyarı görmek normaldir (DEBUG, SSL, güvenli çerezler).

---

## 10. Bilinen sınırlar

Şeffaflık gereği açıkça belirtiyoruz:

| Sınır | Etki | Azaltma |
|---|---|---|
| `RateLimitMiddleware` süreç içi bellek kullanır | Çok işçili dağıtımda limit işçi başına uygulanır | Redis tabanlı çözüme geçin |
| `InMemoryChannelLayer` tek süreçlidir | Çok sunuculu kurulumda WebSocket yayını paylaşılmaz | `CHANNEL_LAYER=redis` |
| SQLite eşzamanlı yazmada sınırlıdır | Yoğun çok terminalli kullanımda kilitlenme | PostgreSQL'e geçin |
| Ödeme cihazı entegrasyonu yoktur | Kart ödemesi elle kaydedilir | POS terminali entegrasyonu ileriki sürümde |
| e-Fatura/ÖKC entegrasyonu yoktur | Yasal mali belge üretilmez | Yetkili entegratör bağlanmalı |
| CSP `unsafe-inline` içerir | XSS savunması bir miktar zayıflar | Alpine.js gereksinimi; nonce tabanlı CSP ileriki sürümde |
| Yerel AI modeli yanlış yanıt verebilir | Analiz yorumları hatalı olabilir | Sayılar deterministik hesaplanır; yorumlar güven düzeyiyle sunulur |

---

## 11. Güvenlik testleri

Güvenlik testleri `tests/test_security.py`,
`tests/test_pin_and_bootstrap_security.py` ve
`tests/test_pii_masking_regression.py` dosyalarındadır. Güncel sayı için
`python scripts/project_metrics.py` çalıştırın; bu belgeye elle sayı
yazılmaz. Kapsanan başlıklar:

- Tehlikeli terminal komutlarının engellendiği
- Güvenli komutlara izin verildiği
- Yan etkili komutların onay istediği
- Yol geçişi ve kök dışı mutlak yol reddi
- Korumalı dosyaların düzenlenemediği
- Alt süreç ortamında gizli değer bulunmadığı
- Güvenlik başlıklarının varlığı
- Tüm modüllerde giriş zorunluluğu
- CSRF zorunluluğu
- Denetim kaydının değiştirilemezliği
- Parola politikası
- Dosya yükleme magic byte kontrolü
- KVKK maskeleme ve anonimleştirme

```powershell
python -m pytest tests/test_security.py -v
python -m bandit -c pyproject.toml -r apps config
python -m pip_audit
```

---

## 12. Bağımlılık güvenliği

Bağımlılıklar `pip-audit` ile taranır. Tarama **bir anlık görüntüdür**:
bugün temiz çıkan bir sürüm yarın açıklanan bir zafiyetle etkilenebilir. Bu
yüzden burada "açık yoktur" denmez; taramayı siz de çalıştırın:

```powershell
python -m pip_audit
```

GitHub Actions iş akışı her push ve pull request'te bu taramayı otomatik
çalıştırır.
