# Yönetici Kılavuzu

Sistem yöneticileri ve işletme sahipleri için. Günlük kullanım için
[USER_GUIDE.md](USER_GUIDE.md) belgesine bakın.

---

## 1. İlk kurulum sırası

Sistemi yeni kurdunuzda şu sırayı izleyin:

1. **Yönetici hesabı** — `python manage.py createsuperuser`
2. **Bölümler ve masalar** — Masalar → Masa yönetimi
3. **Mutfak istasyonları** — Mutfak → İstasyonlar
4. **Depolar** — varsayılan "Ana Depo" otomatik oluşur; gerekirse ekleyin
5. **Ölçü birimleri** — g, kg, ml, lt, adet
6. **Malzemeler** — kritik seviye ve raf ömrü ile
7. **Açılış stoğu** — her malzeme için stok girişi
8. **Menü kategorileri**
9. **Ürünler** — fiyat, KDV, hazırlık istasyonu, alerjenler
10. **Reçeteler** — maliyet ve otomatik stok düşümü için **kritik**
11. **Personel hesapları** — rol atayarak
12. **PIN kodları** — yetkili onayı gerektiren roller için

> Yapıyı görmek için önce `python manage.py seed_demo` ile demo veriyi
> yükleyip inceleyebilir, sonra `--reset` ile temizleyebilirsiniz.

---

## 2. Kullanıcı ve yetki yönetimi

### Yeni kullanıcı

**Ayarlar → Kullanıcılar → Yeni kullanıcı**

Rol seçtiğinizde ilgili izinler otomatik atanır. **Parola değiştirmeli**
kutusunu işaretlerseniz kullanıcı ilk girişte parolasını değiştirmek zorunda
kalır.

**POS PIN kodu** şu roller için tanımlanmalıdır: işletme sahibi, genel müdür,
restoran müdürü, şef garson, kasiyer — çünkü iptal/iade/indirim onayı bu
kişilerden istenir.

### Roller ve tipik yetkileri

| Rol | Öne çıkan yetkiler |
|---|---|
| İşletme sahibi | **Tümü** (Geliştirme Merkezi dahil) |
| Genel müdür | Tümü (Geliştirme Merkezi hariç) + kullanıcı yönetimi |
| Restoran müdürü | Operasyon + iade/iptal onayı + mali raporlar + ayarlar |
| Şef | Menü, reçete, stok, satın alma, mutfak, vardiya planı |
| Mutfak personeli | Mutfak ekranı, menü ve reçete görüntüleme |
| Şef garson | POS + iptal/indirim + masa yönetimi + rezervasyon |
| Garson | POS kullanımı, masa ve rezervasyon görüntüleme |
| Kasiyer | POS, kasa, sadakat, müşteri, temel raporlar |
| Bar personeli | Bar ekranı, POS, stok görüntüleme, fire kaydı |
| Depo / satın alma | Stok, sayım, fire, tedarikçi, satın alma |
| Muhasebe | Mali raporlar, gelir/gider, kasa, denetim kayıtları |
| Kurye | Teslimat panosu |

### İzin ince ayarı

**Kullanıcılar → 🔑 (İzinler)** ekranında iki liste vardır:

- **Ek izinler** — rolde olmayan bir yetkiyi bu kişiye verir
- **Kapatılan izinler** — rolde olsa bile bu kişiye kapatır (**önceliklidir**)

Örnek: Deneyimli bir garsona iptal yetkisi vermek → `pos.void` ek izin.
Yeni bir müdüre iade yetkisi vermemek → `pos.refund` kapatılan izin.

Tüm izin değişiklikleri denetim kaydına yazılır.

### Hesap devre dışı bırakma

Personel ayrıldığında hesabı **silmeyin** — devre dışı bırakın (⊘ düğmesi).
Böylece geçmiş adisyonlardaki izler korunur.

---

## 3. Kasa yönetimi

### Vardiya başında

**POS → Kasa → Kasayı aç**: terminal adı ve açılış kasası (bozuk para) girin.

> Kasa açık değilken ödeme alınabilir ancak nakit takibi yapılamaz. Vardiya
> başında mutlaka açın.

### Vardiya sonunda

**Kasayı kapat**: fiziksel olarak saydığınız nakdi girin.

Sistem hesaplar:

```
Beklenen nakit = açılış kasası + nakit tahsilat − nakit iade + kasa hareketleri
Fark           = sayılan − beklenen
```

50 ₺'yi aşan farklar denetim kaydına **uyarı** olarak düşer.

Kasa kapandığında **gün sonu raporu otomatik oluşturulur.**

### Kasa hareketleri

Gün içinde kasadan para çıkışı (tedarikçiye ödeme, market alışverişi) veya
girişi olduğunda **Kasa hareketi ekle** ile kaydedin. Aksi hâlde kapanışta
fark çıkar.

---

## 4. Gün sonu ve raporlama

### Gün sonu raporu

Kasa kapanışında otomatik oluşur veya **Raporlar → Gün Sonu → Rapor oluştur**
ile elle üretilir.

İçerik: sipariş/misafir sayısı · brüt satış · indirim · iade · servis bedeli ·
KDV · net satış · bahşiş · ortalama adisyon · iptal sayısı ve tutarı ·
ödeme dağılımı · kategori dağılımı · kasa farkı.

PDF olarak indirilebilir.

> ⚖️ Bu belge **yasal Z raporu değildir.** Yasal Z raporu onaylı ÖKC cihazı
> tarafından üretilmelidir.

### Kârlılık takibi

**Raporlar → Kârlılık** ürün bazında ciro, maliyet, kâr ve marj gösterir.

Dikkat edilecekler:

- **Reçetesiz ürünler** — maliyeti sıfır sayılır, kâr olduğundan yüksek görünür.
  Sayfa üstünde kaç ürünün reçetesiz olduğu uyarı olarak çıkar.
- **Gıda maliyet oranı** hedefi %25-35'tir. %40 üzeri ürünleri gözden geçirin:
  porsiyon küçültme, tedarikçi değiştirme veya fiyat artışı.
- **Marj %40'ın altındaki** ürünler kırmızı gösterilir.

### İstatistik merkezi

**İstatistik** menüsü, tek bir raporun ötesinde **karşılaştırmalı** bakış
sunar: seçtiğiniz dönem, hemen önceki eşit uzunlukta dönemle yan yana
konur. Yetki: `report.statistics`.

Bölümler:

| Bölüm | Ne işe yarar |
|---|---|
| 8 karşılaştırmalı ölçüt | Ciro, sipariş, ortalama sepet, misafir, kişi başı, günlük ortalama, indirim, KDV hariç ciro — her biri önceki dönemle yüzde farkıyla |
| Günlük eğilim | Bu dönem ile önceki dönem aynı eksende (kesik çizgi) |
| Aylık eğilim | Son 12 ayın gidişatı |
| **Gün × saat matrisi** | Personel planlaması: hangi gün hangi saatte kaç sipariş |
| Haftanın günleri | Günlük **ortalama** performans |
| Müşteri | Yeni/tekrar eden oranı, en değerli müşteriler, tanımlama oranı |
| Stok ve fire | Fire tutarı ve oranı, tüketim, mevcut stok değeri |
| Servis | Ortalama servis süresi, masa devir hızı, en yoğun gün |

**Gün × saat matrisini okurken:** hücreler toplam değil **ortalama**
sipariş sayısıdır. Bir gün 30 günlük aralıkta 4 veya 5 kez geçebilir;
ham toplam bu yüzden yanıltıcı olur.

> **Soluk gösterilen hücrelere göre karar vermeyin.** Üç günden az
> gözleme dayanan hücreler soluklaştırılır: tek bir kalabalık akşam,
> düzenli bir örüntü gibi görünebilir. Aynı şey haftanın günleri
> tablosundaki soluk satırlar için de geçerlidir. Personel planını
> yalnızca koyu hücrelere dayandırın; kısa aralık seçtiyseniz önce
> aralığı genişletin.

Haftanın günleri tablosunda "gözlenen gün" sayısı, en yoğun gün kartında
ise hangi tarihe ait olduğu açıkça yazar — sayının hangi veri hacminden
geldiğini görmeden yorumlamayın.

Tüm bölümler **Excel** düğmesiyle çok sayfalı bir dosyaya aktarılır.

### Denetim raporu

**Raporlar → İptal, İndirim ve İade** kullanıcı bazında dağılımı gösterir.

> Yüksek sayılar tek başına usulsüzlük kanıtı **değildir**. Yoğun vardiya,
> yetki dağılımı veya operasyonel sorunlardan da kaynaklanabilir. Sayfa
> içindeki **AI anormallik taraması** her bulgu için masum bir açıklama
> olasılığını da belirtir.

---

## 5. Sistem ayarları

**Ayarlar** ekranı iki bölümdür:

- **`.env` dosyasından gelenler** (salt okunur): işletme adı, para birimi,
  KDV oranı, servis bedeli, ortam, veritabanı. Değiştirmek için `.env`
  dosyasını düzenleyip uygulamayı yeniden başlatın.
- **Çalışma zamanı ayarları** (düzenlenebilir): sadakat puan oranı, rezervasyon
  hatırlatma süresi, masa temizlik süresi vb.

Her ayar değişikliği eski ve yeni değeriyle birlikte denetim kaydına yazılır.

---

## 6. Yedekleme ve geri yükleme

Üç yol vardır. **Uygulama içi yedekleme** önerilendir; komut satırı
gerektirmez ve paketlenmiş `.exe` sürümde de çalışır.

### 6.1 Uygulama içinden (önerilen)

**Yedekleme** menüsü → **Yedek al**. Yetki: `backup.create`
(restoran müdürü ve üstü).

Arşive girenler:

| İçerik | Açıklama |
|---|---|
| Veritabanı | Tutarlı anlık görüntü (SQLite yedekleme API'si / `pg_dump`) |
| `veri.json` | Taşınabilir Django dökümü — farklı kuruluma/PostgreSQL'e taşımak için |
| Yüklenen dosyalar | `media/` klasörü (isteğe bağlı, boyut sınırlı) |
| `manifest.json` | Ne zaman, kim, hangi sürüm, hangi içerik |

**API anahtarları (`.env`) varsayılan olarak yedeğe girmez.** Yedek arşivi
çoğu zaman e-postayla veya bulutla taşınır; anahtarların bu yolla sızması
gerçek bir risktir. Gerekiyorsa `.env` içinde `BACKUP_ALLOW_SECRETS=True`
yapın; arşiv o zaman listede **"gizli ayarlar"** rozetiyle işaretlenir.

Her yedeğin SHA-256 özeti saklanır. Ayrıntı ekranında **Dosya bütünlüğü**
satırı, dosyanın alındığından beri değişip değişmediğini söyler.

### 6.2 Otomatik yedekleme

`.env` içinde:

```ini
BACKUP_SCHEDULE_ENABLED=True
BACKUP_SCHEDULE_HOURS=24
BACKUP_KEEP_LAST=20
```

Sunucu çalışırken arka planda çalışır. Yedek alınamazsa yöneticilere
bildirim düşer — sessizce başarısız olmaz.

Sunucunun sürekli açık olmadığı kurulumlarda Görev Zamanlayıcı kullanın:

```powershell
$action = New-ScheduledTaskAction -Execute "D:\Restaurant\.venv\Scripts\python.exe" `
    -Argument "manage.py backup_now --if-due" -WorkingDirectory "D:\Restaurant"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "Restaurant Yedek" -Action $action -Trigger $trigger
```

`--if-due` yalnızca aralık dolduysa yedek alır; gereksiz kopya üretmez.

### 6.3 Komut satırından

```powershell
.\.venv\Scripts\python.exe manage.py backup_now --note "surum yukseltme oncesi"
```

Eski `backup.ps1` / `restore.ps1` scriptleri de durmaktadır; sanal ortam
kurulu geliştirme ortamları için uygundur.

### 6.4 Geri yükleme

**Yedekleme** → yedeğe tıkla → **Geri yükle**. Yetki: `backup.restore`
(genel müdür ve işletme sahibi).

Sıra şudur:

1. Arşiv doğrulanır (manifest, sağlama toplamı, veritabanı motoru uyumu)
2. **Mevcut durumun güvenlik yedeği alınır** — bu adım başarısız olursa
   işlem hiç başlamaz
3. Onay kutusuna `GERİ YÜKLE` yazılmış olmalıdır
4. Veritabanı ve yüklenen dosyalar geri yazılır
5. Yedek kayıtları diskle yeniden eşitlenir, böylece güvenlik yedeği
   listede görünür ve gerekirse ona dönebilirsiniz

Geri yüklemeden sonra **çıkış yapıp yeniden giriş yapın**: oturumunuz
yedekten önceki kullanıcı kaydına ait olabilir.

> **Farklı veritabanı motorları arasında ham geri yükleme yapılamaz.**
> SQLite yedeğini PostgreSQL'e taşımak için arşivdeki `veri.json`
> dosyasını `manage.py loaddata` ile içe aktarın.

### 6.5 Bunları yapmayı unutmayın

- **Yedeği başka bir diske kopyalayın.** Aynı diskteki yedek, disk
  arızasına karşı koruma sağlamaz.
- **Yedeğinizin geri yüklenebildiğini düzenli olarak test edin.** Test
  edilmemiş yedek, yedek değildir.
- Yedek dosyası **tüm müşteri kişisel verilerini** içerir ve
  şifrelenmemiştir. KVKK açısından fiziksel güvenliği sizin
  sorumluluğunuzdadır.

---

### 6.6 Kişisel veri saklama süreleri (KVKK)

Denetim kayıtlarındaki IP adresleri, rıza kayıtlarındaki IP'ler ve
sonuçlanmış rezervasyon/bekleme listesi kayıtlarındaki misafir bilgileri
için saklama süresi tanımlayabilirsiniz. Süreler `.env` dosyasındaki
`RETENTION_*` değişkenleriyle GÜN cinsinden ayarlanır (0 = kapalı) —
uygun süreyi veri sorumlunuzla (varsa DPO/hukuk danışmanı) birlikte
belirleyin; uygulama bir süre dayatmaz.

Temizlik kayıt SİLMEZ; yalnızca kişisel veri alanlarını boşaltır
(ör. rezervasyon "Anonim Misafir" olur, sayısal istatistikler korunur):

```bash
python manage.py purge_expired_logs
```

Bu komut yalnızca önizleme gösterir. Uygulamak için `--apply` ekleyin;
her uygulama denetim kaydına kanıt olarak işlenir. Komutu aylık bakım
listesine ekleyebilir veya Görev Zamanlayıcı'ya bağlayabilirsiniz.

---

## 7. Bakım

### Haftalık

- [ ] Kritik stok uyarılarını gözden geçirin
- [ ] Son kullanma tarihi yaklaşan partileri kontrol edin
- [ ] Olumsuz yorumları yanıtlayın
- [ ] Kasa farklarını inceleyin

### Aylık

- [ ] Stok sayımı yapın ve uygulayın
- [ ] Kârlılık raporunu inceleyin, düşük marjlı ürünleri gözden geçirin
- [ ] Menü mühendisliği analizini çalıştırın
- [ ] Reçetesiz ürünleri tamamlayın
- [ ] İptal/indirim raporunu denetleyin
- [ ] Yedeğin geri yüklenebildiğini test edin

### Üç aylık

- [ ] Bağımlılıkları güncelleyin ve tarayın: `python -m pip_audit`
- [ ] Kullanıcı listesini gözden geçirin, ayrılanları devre dışı bırakın
- [ ] İzin dağılımını kontrol edin
- [ ] Denetim kayıtlarını inceleyin
- [ ] Tedarikçi fiyatlarını ve reçete maliyetlerini güncelleyin

---

## 8. Performans

### SQLite'tan PostgreSQL'e geçiş

3'ten fazla eşzamanlı terminal kullanıyorsanız veya "database is locked"
hataları görüyorsanız geçin:

```powershell
# 1) Mevcut veriyi dışa aktarın
python manage.py dumpdata --natural-foreign --natural-primary `
    -e contenttypes -e auth.Permission -e sessions -e axes `
    --indent 2 -o veri.json

# 2) .env içinde DB_ENGINE=postgres yapın ve bağlantı bilgilerini girin

# 3) Yeni veritabanında tabloları oluşturun
python manage.py migrate

# 4) Veriyi içe aktarın
python manage.py loaddata veri.json
```

> Bu dosya müşteri verisi içerir — işlem sonrası **silin**.

### Çok sunuculu dağıtım

```env
CHANNEL_LAYER=redis
REDIS_URL=redis://127.0.0.1:6379/0
```

```powershell
pip install channels-redis
```

Aksi hâlde her sunucu kendi WebSocket grubunu tutar ve mutfak ekranları
senkronize olmaz.

---

## 9. Yapay zekâ yönetimi

### Bütçe

```env
AI_DAILY_BUDGET_USD=1.00
AI_MONTHLY_BUDGET_USD=20.00
```

Bütçe dolduğunda bulut çağrıları durur ve sistem yerel modele düşer.
Kullanım ve maliyet: **Yapay Zekâ → Kullanım**

### Gizlilik

Varsayılan ayarları **değiştirmemeniz önerilir**:

```env
AI_MASK_PII=True              # kişisel veriyi istemden temizle
AI_SENSITIVE_LOCAL_ONLY=True  # hassas görevleri buluta gönderme
AI_ROUTING_POLICY=local_first # önce yerel model
```

Tam gizlilik için `AI_ROUTING_POLICY=local_only` yapın — hiçbir veri
internete çıkmaz.

### Sağlayıcı sorunları

**Yapay Zekâ → Sağlayıcılar** ekranından test edin. Bir sağlayıcı art arda
3 kez başarısız olursa **devre kesici** açılır ve 2 dakika devre dışı kalır.
Sorunu çözdükten sonra **Devre kesicileri sıfırla** deyin.

---

## 10. AI Geliştirme Merkezi (dikkatli kullanın)

Bu bölüm kod çalıştırabildiği için **en yüksek riskli** alandır.

### Ne zaman açık olmalı?

| Ortam | Öneri |
|---|---|
| Geliştirme makinesi | Açık olabilir |
| Test sunucusu | Kapalı |
| **Üretim (canlı restoran)** | **Kesinlikle kapalı** |

```env
DEVCENTER_ENABLED=False
DEVCENTER_TERMINAL_ENABLED=False
```

### Güvenli kullanım

1. Bir değişiklik önerisi oluşturun.
2. **Diff'i satır satır okuyun** — "onayla" demeden önce ne değiştiğini anlayın.
3. **Testleri çalıştırın.** Testler başarısızsa sistem uygulamayı zaten
   reddeder.
4. **Ayrı Git dalı oluştur** seçeneğini işaretli bırakın.
5. Uygulamadan sonra uygulamayı elle test edin.
6. Sorun varsa **Geri Al** düğmesiyle önceki duruma dönün.

Her uygulama kritik seviyede denetim kaydı bırakır.

---

## 11. Sorun giderme

| Belirti | Olası neden | Çözüm |
|---|---|---|
| Mutfak ekranı güncellenmiyor | WebSocket kopuk | Sağ üstteki durum göstergesine bakın; sunucuyu yeniden başlatın |
| Stok yanlış görünüyor | Elle düzeltme yapılmış | Stok hareketleri ekranından geçmişi inceleyin, sayım yapın |
| Ürün satışa kapandı | Malzeme stoğu bitti | Stok girişi yapın, ürün otomatik açılır |
| Kasa farkı büyük | Kasa hareketi kaydedilmemiş | Gün içi para giriş/çıkışlarını kaydedin |
| Kârlılık raporu şişkin | Reçetesiz ürünler | Eksik reçeteleri tamamlayın |
| Kullanıcı giremiyor | 5 hatalı deneme sonrası kilit | 1 saat bekleyin veya Django yönetiminden Axes kaydını silin |
| AI yanıt vermiyor | LM Studio kapalı | Developer → Start Server |
| AI yanıtı boş | Muhakeme modeli token sınırı | `AI_MAX_TOKENS=4000` yapın |
| Sayfa stilsiz | Statik dosyalar eksik | `python manage.py collectstatic --noinput` |

### Sağlık kontrolü

```
GET http://127.0.0.1:8000/healthz/
```

```json
{"status": "ok", "database": true}
```

### Günlükler

```
logs\restaurant.log   — genel uygulama
logs\security.log     — giriş, yetki, güvenlik olayları
```

API anahtarları ve kişisel veriler bu dosyalarda otomatik maskelenir.

---

## 12. Üretime alma

Sistemi gerçek restoran işleyişine almadan önce
[SECURITY.md § 9 Üretim kontrol listesi](SECURITY.md#9-üretim-kontrol-listesi)
bölümündeki maddelerin **tamamını** uygulayın.

Özet:

```env
DJANGO_ENV=production
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<güçlü ve benzersiz>
DJANGO_ALLOWED_HOSTS=restoran.example.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
DEVCENTER_ENABLED=False
DEVCENTER_TERMINAL_ENABLED=False
DB_ENGINE=postgres
```

Doğrulama:

```powershell
python manage.py check --deploy
```

Bu komut üretim yapılandırmasında **hiçbir uyarı vermemelidir.**

Son olarak: **demo hesaplarını silin.**

```powershell
python manage.py seed_demo --reset
python manage.py createsuperuser
```
