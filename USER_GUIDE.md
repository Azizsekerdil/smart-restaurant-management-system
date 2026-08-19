# Kullanım Kılavuzu

Günlük operasyonda sistemin nasıl kullanılacağını anlatır. Yönetici işlemleri
için [ADMIN_GUIDE.md](ADMIN_GUIDE.md) belgesine bakın.

---

## Giriş ve genel gezinme

Tarayıcıdan `http://127.0.0.1:8000` adresini açın ve kullanıcı adınız veya
e-postanızla giriş yapın.

Girişten sonra **rolünüze uygun ekrana** otomatik yönlendirilirsiniz:
garson → POS · mutfak personeli → mutfak ekranı · yönetici → panel.

Sol menüde yalnızca **yetkiniz olan** bölümler görünür.

### Klavye kısayolları

| Tuş | Ekran |
|---|---|
| `Alt + P` | POS |
| `Alt + M` | Masa planı |
| `Alt + K` | Mutfak ekranı |
| `Alt + D` | Yönetim paneli |
| `Alt + S` | Stok |
| `Shift + ?` | Kısayol listesi |

### Tema

Sağ üstteki ◐ düğmesi açık/koyu tema arasında geçiş yapar. Tercihiniz
tarayıcıda saklanır. Mutfak ekranı için koyu tema önerilir.

---

## POS — Satış ekranı

### Yeni adisyon açma

1. **POS** ekranında sağ üstteki **+** düğmesine basın.
2. Sipariş türünü seçin:
   - **Masada servis** → masa seçimi zorunludur
   - **Paket** / **Gel-al** / **Kurye** → masa gerekmez
3. Kişi sayısını girin.
4. İsterseniz müşteri arayın (ad, telefon veya müşteri kodu ile).
   Müşterinin **alerji notu varsa adisyon panelinde kırmızı uyarı çıkar.**
5. **Adisyon aç** düğmesine basın.

> Masaya tıklayarak da adisyon açabilirsiniz: **Masalar** ekranından masayı
> seçip **Adisyon aç** deyin. Masada zaten açık adisyon varsa o adisyon açılır.

### Ürün ekleme

- Ürün kartına dokunun — adisyona 1 adet eklenir.
- Üstteki arama kutusuna ürün adı veya stok kodu yazarak filtreleyin.
- Kategori şeritlerinden filtreleyin.
- Adet değiştirmek için adisyon panelindeki **−** / **+** düğmelerini kullanın.

**Kırmızı kenarlıklı ve soluk görünen ürünler satışa kapalıdır.** Üzerine
gelince nedenini görürsünüz (genellikle malzeme stoğu bitmiştir).

### Mutfağa gönderme

**Mutfağa gönder** düğmesine basın. Bu anda:

- Siparişler **istasyona göre otomatik ayrılır** — yemekler mutfağa,
  içecekler bara ayrı KOT olarak gider
- **Reçeteye göre stok otomatik düşer**
- Mutfak ekranında sipariş anında belirir ve sesli uyarı verir

Sonradan ürün eklerseniz tekrar **Mutfağa gönder** deyin — yalnızca **yeni
satırlar** gönderilir, eskiler tekrarlanmaz.

### İndirim uygulama

**%** düğmesine basın:

- **Elle** sekmesi: yüzde **veya** tutar girin. **Gerekçe zorunludur.**
- **Kupon** sekmesi: kupon kodunu yazın.

İndirim yetkiniz yoksa sistem **yetkili onayı** ister: bir yöneticinin
kullanıcı adı ve PIN'i girilir. Tüm indirimler kim tarafından, hangi gerekçeyle
yapıldığı kaydedilerek denetim kaydına işlenir.

### Hesap bölme

**✂** düğmesine basın ve yöntemi seçin:

| Yöntem | Ne yapar |
|---|---|
| **Eşit böl** | Toplamı N kişiye böler, yuvarlama farkını son kişiye ekler |
| **Koltuk numarasına göre** | Her koltuğun tutarını ayrı listeler |
| **Seçili ürünleri ayır** | İşaretlenen satırları **yeni bir adisyona** taşır |

"Seçili ürünleri ayır" için önce adisyon panelinde satırların yanındaki
kutucukları işaretleyin. En az bir satır ana adisyonda kalmalıdır.

### Ödeme alma

1. **Ödeme al** düğmesine basın.
2. Ödeme yöntemini seçin.
3. Tutarı girin — varsayılan olarak kalan bakiye gelir.
4. Nakit ödemede **alınan tutarı** girin; para üstü otomatik hesaplanır.
   Sayı tuş takımını kullanabilirsiniz.
5. **Ödemeyi tamamla**.

**Çoklu ödeme:** Müşteri bir kısmını kartla, kalanını nakit ödeyecekse önce
kart tutarını girip tamamlayın; adisyon açık kalır ve kalan bakiye görünür.
Ardından ikinci ödemeyi alın. Adisyon **tamamen ödendiğinde** otomatik kapanır
ve masa "temizlikte" durumuna geçer.

### Fiş yazdırma

🖨 düğmesi 80 mm termal yazıcıya uygun fişi yeni sekmede açar ve yazdırma
penceresini başlatır. PDF için adisyon detay sayfasındaki PDF düğmesini
kullanın.

> Bu fiş **bilgi fişidir**, yasal mali belge değildir.

### İptal

- **Tek satır:** satırın yanındaki 🗑 düğmesi
- **Tüm adisyon:** adisyon detay sayfasından

Her iki durumda **gerekçe zorunludur** ve yetkiniz yoksa yetkili onayı istenir.
Mutfağa gitmiş bir satır iptal edilirse **stok otomatik geri yüklenir**.

---

## Mutfak ekranı (KDS)

**Mutfak** menüsünden açılır. Tam ekran (`F11`) çalıştırmanız önerilir.

### Ekranı okuma

Her kart bir KOT'tur (mutfak fişi):

- **Üst satır:** masa adı, KOT numarası, istasyon
- **Sağ üst:** geçen süre — **canlı sayar**
- **Orta:** ürünler; `+` ile ekstra malzemeler, `!` ile müşteri notu
- **Alt:** işlem düğmeleri

**Renk kodu:**

| Renk | Anlam |
|---|---|
| Normal | Süre içinde |
| 🟡 Sarı | Uyarı süresi aşıldı |
| 🔴 Kırmızı + yanıp sönme + sesli uyarı | Kritik süre aşıldı |

Süre eşikleri her istasyon için ayrı ayarlanır.

### İş akışı

```
Sırada  ──[Başla]──►  Hazırlanıyor  ──[Hazır]──►  Hazır  ──[Teslim edildi]──►  Tamamlandı
```

**Hazır** dendiğinde garsona otomatik bildirim gider.

- ⚡ düğmesi KOT'u **acil** sıraya alır (listede en üste çıkar).
- 🖨 düğmesi KOT'u yazdırır.

### Filtreleme

Üstteki istasyon düğmeleriyle yalnızca kendi istasyonunuzu görüntüleyin.
Bar personeli yalnızca bar istasyonunu görebilir.

### Bağlantı durumu

Sağ üstte:

- 🟢 **Canlı** — WebSocket bağlı, siparişler anında düşüyor
- ⚪ **Bağlantı koptu** — otomatik yeniden bağlanma denenir; bu sırada ekran
  30 saniyede bir kendini yeniler, sipariş kaybolmaz

🔊 düğmesi sesli uyarıyı açıp kapatır.

---

## Masa planı

**Masalar** menüsünden açılır. Her bölüm ayrı bir plan olarak gösterilir.

| Renk | Durum |
|---|---|
| 🟢 Yeşil | Boş |
| 🔴 Kırmızı | Dolu (kaç dakikadır dolu olduğu yazar) |
| 🟡 Sarı | Rezerve |
| 🔵 Mavi | Temizlikte |
| ⚪ Gri | Kullanım dışı |

Masaya tıkladığınızda:

- **Adisyon aç / görüntüle** → POS ekranına gider
- **Durum değiştir** → temizlik bittiğinde masayı boşa alın
- **Garson ata**
- **QR menü kodu** → masaya yapıştırmak için QR kodu açar

Sayfa 90 saniyede bir kendini yeniler.

> Masada açık adisyon varken masa "boş" yapılamaz — önce adisyonu kapatın.

---

## Rezervasyon

**Rezervasyon** menüsünden yönetilir.

### Yeni rezervasyon

**Yeni rezervasyon** → misafir adı, telefon, kişi sayısı, tarih-saat ve süre
girin. Masa seçimi isteğe bağlıdır; misafir geldiğinde masa planından da
atayabilirsiniz.

Seçilen masaların toplam kapasitesi kişi sayısından az olamaz — sistem uyarır.

**Özel gün** alanına "Doğum günü" gibi bir not yazarsanız listede rozet olarak
görünür. **Alerji notu** servis sırasında uyarı olarak çıkar.

### Misafir geldiğinde

Listede rezervasyonun yanındaki:

- 👤✓ **Oturdu** — masaları dolu işaretler
- 👤✗ **Gelmedi** — no-show kaydı düşer, masaları serbest bırakır

15 dakikadan fazla gecikmiş rezervasyonlar listede **sarı** görünür.

### Bekleme listesi

Rezervasyonsuz gelen ve masa bekleyen misafirler için sağdaki panele misafir
adı, kişi sayısı ve telefon girin. Masa boşaldığında 🔔 düğmesiyle "çağrıldı"
olarak işaretleyin. Bekleme süresi otomatik sayılır.

---

## Stok

### Stok listesi

**Stok** menüsü tüm malzemeleri ve güncel durumlarını gösterir:

| Durum | Anlam |
|---|---|
| **Normal** | Kritik seviyenin üzerinde |
| **Azalıyor** | Kritik seviyenin %150'sinin altında |
| **Kritik** | Kritik seviyenin altında |
| **Tükendi** | Stok sıfır veya altında |

**Tahminî gün** sütunu, son 30 günün ortalama tüketim hızına göre stoğun kaç
gün yeteceğini gösterir.

### Stok girişi

Malzeme detayına girin → **Stok girişi**:

- Miktar ve **birim** — kg girerseniz sistem otomatik grama çevirir
- Birim maliyet
- Depo
- Son kullanma tarihi (bozulabilir malzemelerde raf ömründen otomatik hesaplanır)
- Parti kodu

Her giriş ayrı bir **parti** oluşturur. Tüketimde partiler FIFO veya FEFO
sırasına göre kullanılır ve **her partinin kendi maliyeti** hesaba katılır.

### Fire kaydı

**Stok → Fire ve İsraf → Fire kaydı**: malzeme, miktar, neden ve açıklama
girin. Stok düşer ve maliyet otomatik hesaplanır. 500 ₺ üzeri fireler
yöneticilere bildirilir.

### Sayım

**Stok → Sayım → Yeni sayım**: depo seçin. Sistem tüm malzemeleri sistem
miktarıyla listeler.

1. Fiziksel sayımı yapın, **sayılan miktar** sütununa girin.
2. **Sayımı kaydet** — istediğiniz kadar ara kayıt yapabilirsiniz.
3. Bittiğinde **Sayımı uygula** — farklar stok hareketine dönüşür.

> "Sayımı uygula" **geri alınamaz** ve onay ister.

### Uyarılar

**Stok → Uyarılar** ekranı kritik seviyedeki malzemeleri ve son kullanma
tarihi yaklaşan partileri bir arada gösterir. **Otomatik sipariş taslağı
oluştur** düğmesi, kritik malzemeler için tedarikçi bazında satın alma
taslakları hazırlar.

---

## Menü yönetimi

### Ürün ekleme

**Menü → Yeni ürün**: ad, kategori, **KDV dahil satış fiyatı**, hazırlık
süresi ve **hazırlık istasyonu** girin.

> İstasyon seçimi önemlidir — sipariş bu istasyonun mutfak ekranına düşer.

Alerjenleri işaretleyin; QR menüde ve müşteri uyarılarında gösterilir.

### Reçete

Ürün detayında **Reçete → Düzenle**:

- Her satıra bir malzeme, miktar ve birim girin
- **Fire oranı**: hazırlıktaki kayıp (soyma, temizleme). %10 girerseniz
  stoktan %10 fazla düşer
- **Verim**: bu reçete kaç porsiyon üretiyorsa yazın
- **İşçilik** ve **genel gider** payı ekleyebilirsiniz

Kaydettiğinizde porsiyon maliyeti, kâr marjı ve gıda maliyet oranı anında
hesaplanır. Hedef gıda maliyet oranı **%25-35**'tir.

> Reçetesi olmayan ürünlerde otomatik stok düşümü **çalışmaz** ve kârlılık
> raporunda maliyet sıfır görünür.

### Ürünü satışa kapatma

Ürün listesindeki ⏸ düğmesi ürünü satışa kapatır. Malzemesi biten ürünler
**otomatik olarak kapanır**, stok girişi yapıldığında **otomatik açılır**.

---

## Müşteriler

### Müşteri kaydı

**Müşteriler → Yeni müşteri**. Alerji notu girerseniz POS'ta adisyon açılırken
kırmızı uyarı olarak görünür.

### KVKK izinleri

Müşteri detayında her izin türü için ✓ / ✗ düğmeleri vardır. Tüm izin
değişiklikleri zaman damgasıyla kaydedilir.

Müşteri "verilerimi silin" derse: **KVKK — verileri anonimleştir**. Kişisel
bilgiler geri döndürülemez şekilde silinir, sipariş geçmişi anonim olarak
korunur. Bu işlem özel yetki gerektirir.

### Sadakat

Sipariş kapandığında puan otomatik verilir (varsayılan: 100 ₺ = 10 puan).
Müşteri seviyesi (Bronz/Gümüş/Altın/Platin) toplam harcamaya göre yükselir ve
puan kazanımını artırır.

Elle puan eklemek/düşmek için müşteri detayında **Puan düzelt**.

### Yorumlar

**Müşteriler → Yorumlar**. **AI ile analiz et** düğmesi analiz edilmemiş
yorumları yapay zekâya gönderir; duygu (olumlu/nötr/olumsuz), konu etiketleri
ve kısa özet üretilir.

2 yıldız ve altı yorumlar **sarı** görünür ve çözüm bekler. **Çözüldü**
düğmesiyle not girerek kapatın.

---

## Personel

### Puantaj

**Personel** listesinde her kişinin yanında **Giriş** / **Çıkış** düğmesi
vardır. Çıkışta çalışılan süre otomatik hesaplanır. Vardiya başlangıcından
10 dakika sonra yapılan girişler "geç" olarak işaretlenir.

### Vardiya planı

**Personel → Vardiya**: haftalık ızgara görünüm. Hücredeki **+** ile vardiya
atayın, atanmış vardiyaya tıklayarak kaldırın. Oklarla haftalar arasında
gezinin.

**AI önerisi** düğmesi saatlik yoğunluğa göre kaç personel gerektiğini önerir.

### İzin ve görevler

**İzinler** sekmesinden talep oluşturun; yetkili ✓ / ✗ ile karara bağlar.
**Görevler** sekmesi açılış/kapanış kontrol listeleri için kullanılır.

---

## Raporlar

**Raporlar** menüsü:

| Rapor | İçerik |
|---|---|
| **Satış** | Ürün, kategori, ödeme yöntemi, personel bazında |
| **Kârlılık** | Reçete maliyetine göre ürün bazlı kâr ve marj |
| **İptal/İndirim/İade** | Kullanıcı bazında denetim |
| **Gün sonu** | Kasa kapanış özetleri |
| **Gelir/Gider** | Net kâr ve gider kalemleri |

Tarih aralığını seçip **Uygula** deyin. Sağ üstteki düğmelerle **Excel**,
**PDF** veya **CSV** olarak dışa aktarın. Tüm dışa aktarmalar denetim kaydına
işlenir.

---

## Yapay zekâ asistanı

**Yapay Zekâ** menüsünden açılır.

Sorunuzu doğal dille yazın — sistem **ilgili verilerinizi otomatik olarak
sorguya ekler** ve yanıtı kendi verinize dayandırır.

Örnek sorular:

- "Bugün en çok hangi ürün satıldı?"
- "Bu hafta cirom geçen haftaya göre nasıl?"
- "Hangi malzemeler kritik seviyede?"
- "En kârlı 5 ürünüm hangileri?"
- "Yarın için kaç kişilik personel planlamalıyım?"

Hazır soru düğmelerine tıklayarak da başlayabilirsiniz.

Sol paneldeki **Sağlayıcı** listesinden hangi modelin kullanılacağını
seçebilirsiniz. 🔒 işaretli sağlayıcılar yereldir — veri bilgisayarınızdan
çıkmaz.

### Akıllı analizler

**Yapay Zekâ → Analizler** ekranındaki her kart bir analizi çalıştırır:
menü mühendisliği, talep tahmini, stok tükenme, israf analizi, anormallik
tespiti, personel ihtiyacı, günlük özet, kampanya önerisi.

> Her sonuçta **güven düzeyi**, **veri noktası sayısı** ve **sınırlamalar**
> gösterilir. Tahminler kesin sonuç değildir; karar almadan önce kendi
> değerlendirmenizi yapın.

### Yapay zekâ çalışmıyorsa

"Kullanılabilir bir yapay zekâ sağlayıcısı bulunamadı" mesajı görürseniz
LM Studio'yu açıp **Developer → Start Server** deyin. Ayrıntı için
[README](README.md#lm-studio-kurulumu-yerel-yapay-zekâ).

**Yapay zekâ olmadan da sistemin tamamı çalışır** — yalnızca yorum ve öneri
özellikleri devre dışı kalır, sayısal analizler ve tablolar görünmeye devam
eder.

---

## Bildirimler

Sağ üstteki 🔔 simgesi okunmamış bildirim sayısını gösterir. Bildirim
üretilen durumlar: kritik stok, stok tükenmesi, yüksek tutarlı fire,
sipariş hazır, yüksek oranlı indirim, iade, adisyon iptali.

**Bildirim Merkezi**nden tümünü görüntüleyip okundu işaretleyebilirsiniz.
