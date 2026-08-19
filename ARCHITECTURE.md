# Mimari

Bu belge sistemin teknik yapısını, veri modelini ve önemli tasarım kararlarını
gerekçeleriyle birlikte açıklar.

---

## 1. Genel görünüm

```
┌──────────────────────────────────────────────────────────────┐
│  Tarayıcı                                                    │
│  Bootstrap 5 · HTMX · Alpine.js · Chart.js  (yerel paketli)  │
└───────────┬──────────────────────────────┬───────────────────┘
            │ HTTP                         │ WebSocket
            ▼                              ▼
┌──────────────────────────────────────────────────────────────┐
│  Daphne (ASGI)                                               │
│  ┌────────────────────────┐  ┌────────────────────────────┐  │
│  │ Django (HTTP)          │  │ Channels (WebSocket)       │  │
│  │ · Görünümler           │  │ · KitchenDisplayConsumer   │  │
│  │ · DRF API              │  │ · OrderStreamConsumer      │  │
│  └───────────┬────────────┘  └────────────┬───────────────┘  │
│              │                            │                  │
│              ▼                            │                  │
│  ┌──────────────────────────────────────┐ │                  │
│  │  SERVİS KATMANI (services.py)        │◄┘                  │
│  │  Tüm iş kuralları burada             │                    │
│  │  orders · inventory · kitchen · crm  │                    │
│  └───────────┬──────────────────────────┘                    │
│              ▼                                               │
│  ┌──────────────────────────────────────┐                    │
│  │  MODELLER (Django ORM)               │                    │
│  └───────────┬──────────────────────────┘                    │
└──────────────┼───────────────────────────────────────────────┘
               ▼
      SQLite (WAL) / PostgreSQL

  Yan katman:  apps.ai.gateway → LM Studio / Ollama / NVIDIA / ...
```

---

## 2. Uygulama ayrımı

12 Django uygulaması, iş alanına göre ayrılmıştır:

| Uygulama | Sorumluluk |
|---|---|
| `core` | Taban modeller, denetim kaydı, bildirimler, ara katmanlar, yardımcılar |
| `accounts` | Kullanıcı, roller, izin matrisi, kimlik doğrulama |
| `catalog` | Kategori, ürün, porsiyon, seçenek, alerjen, **reçete** |
| `inventory` | Malzeme, birim, depo, **parti**, hareket, tedarikçi, satın alma, fire |
| `floor` | Salon, masa, rezervasyon, bekleme listesi |
| `orders` | Adisyon, satır, indirim, ödeme, iade, kasa |
| `kitchen` | İstasyon, KOT, KDS tüketicileri |
| `crm` | Müşteri, sadakat, kampanya, yorum, KVKK rızası |
| `hr` | Personel, vardiya, puantaj, izin, görev |
| `reports` | Rapor hesapları, gider, gün sonu, PDF/Excel/CSV |
| `ai` | Sağlayıcı adapterleri, ağ geçidi, akıllı analizler |
| `devcenter` | Güvenli terminal, kod önerisi, geri alma noktaları |

### Neden bu kadar çok uygulama?

İncelenen açık kaynak projelerin çoğu 3-5 uygulama kullanıyor. Bu projede daha
ayrıntılı bir ayrım tercih edildi çünkü:

- Her modül **bağımsız test edilebilir** (`tests/test_inventory.py` yalnızca
  stok mantığını test eder)
- İzin sistemi modül sınırlarıyla örtüşür (`inventory.manage`, `pos.void`)
- İleride bir modül ayrı bir servise taşınabilir (ör. KDS)

---

## 3. Katman kuralı: iş mantığı `services.py` içindedir

Bu, projedeki **en katı kuraldır**:

```
Görünüm (view)  →  Servis (service)  →  Model
API (viewset)   →  Servis (service)  →  Model
Yönetim komutu  →  Servis (service)  →  Model
```

Görünümler yalnızca: istek doğrulama → servis çağırma → yanıt biçimlendirme
yapar. Model üzerinde doğrudan iş kuralı çalıştırmaz.

**Neden:** Aynı kural (ör. "ödenmiş adisyon iptal edilemez") web arayüzünden,
REST API'den ve testlerden aynı şekilde uygulanır. Kural tek yerde durur.

Örnek — sipariş iptali üç yerden çağrılır ama kural tek yerdedir:

```python
# apps/orders/services.py
def cancel_order(order, *, reason, user, restock=True):
    if order.status == Order.Status.PAID:
        raise OrderError("Ödenmiş adisyon iptal edilemez; iade işlemi kullanın.")
    ...
```

---

## 4. Kritik tasarım kararları

### 4.1 Fiyatlar KDV **dahil** saklanır

Türkiye'de menü fiyatları KDV dahil gösterilir. Fiyatı hariç saklayıp kasada
eklemek "menüde 100 ₺ yazıyordu, kasada 118 ₺ çıktı" sorununa yol açar.

Bu yüzden `Product.price` KDV **dahildir** ve vergi geriye doğru hesaplanır:

```
kdv = brüt × oran / (100 + oran)
```

`tests/test_recipes_and_costs.py::test_tax_amount_backed_out_of_inclusive_price`
bu davranışı doğrular.

### 4.2 Sipariş satırında fiyat ve ad **dondurulur**

`OrderItem.product_name` ve `OrderItem.unit_price` sipariş anındaki değerleri
saklar. Menü fiyatı sonradan değişse bile geçmiş adisyonlar ve raporlar
bozulmaz.

`OrderItem.original_price` liste fiyatını da tutar; böylece elle yapılan fiyat
değişiklikleri (`is_price_overridden`) denetlenebilir.

### 4.3 Tutarlar hesaplanıp **modele yazılır**

`Order.recalculate()` tüm tutarları satırlardan hesaplar ve alanlara yazar.
Her istekte yeniden hesaplanmaz.

**Neden:** Rapor sorguları veritabanı tarafında toplama (`Sum`) yapabilir;
binlerce siparişi Python'a çekmek gerekmez.

### 4.4 Stok **parti (lot) bazlıdır**

`StockItem` yalnızca hızlı okuma için tutulan bir özet tablodur. Gerçek kaynak
`StockBatch` (parti) ve `StockMovement` (hareket) kayıtlarıdır.

Bu sayede:

- **FIFO/FEFO** tüketimi mümkün olur (`Ingredient.rotation`)
- Her partinin **kendi maliyeti** vardır → gerçek ağırlıklı ortalama maliyet
- **Son kullanma tarihi** takip edilebilir
- Geriye dönük **izlenebilirlik** sağlanır

Doğrudan `StockItem.quantity` güncellemek **yasaktır**; hareket kaydı bırakmaz.
Tüm değişiklikler `apps/inventory/services.py` üzerinden yapılır.

### 4.5 Reçete tüketiminde negatif stoğa izin verilir

`consume_stock(allow_negative=True)` varsayılandır. Stok kaydı gerçekten
yetmese bile satış **engellenmez**; eksik miktar `shortfall` olarak raporlanır.

**Neden:** Gerçek bir restoranda stok girişi bazen geç yapılır. Kasayı
durdurmak, yanlış stok kaydından çok daha maliyetlidir. Eksiklik uyarı olarak
gösterilir ve sayımda düzeltilir.

Depo transferinde ise `allow_negative=False` kullanılır — olmayan malı başka
depoya göndermek anlamsızdır.

### 4.6 Mali kayıtlar **yumuşak silinir**

`Order`, `Product`, `Customer` gibi modeller `SoftDeleteModel` türetir.
`delete()` çağrısı kaydı silmez, `deleted_at` alanını doldurur.

**Neden:** Denetim ve mali izlenebilirlik. Silinmiş bir adisyonun raporlardan
kaybolması kabul edilemez.

### 4.7 Denetim kaydı **değiştirilemez**

`AuditLog.save()` mevcut bir kaydın güncellenmesini engeller:

```python
if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
    raise ValueError("Denetim kayıtları değiştirilemez.")
```

Ayrıca `username_snapshot` alanı kullanıcı silinse bile izin kaybolmamasını
sağlar.

### 4.8 İzinler **işlev bazlıdır**, model bazlı değil

Django'nun yerleşik izin sistemi CRUD odaklıdır (`add_order`, `change_order`)
ve "garson iptal edemez ama şef garson edebilir" gibi kuralları ifade edemez.

Bunun yerine `apps/accounts/permissions.py` içinde 60+ işlev bazlı izin kodu
(`pos.void`, `report.financial`, `customer.pii`) tanımlanır ve roller bu
kodlarla eşlenir. Değerlendirme sırası:

1. Süper kullanıcı → her şeye izinli
2. `denied_permissions` → kesin ret
3. `extra_permissions` → kesin izin
4. Rol matrisi → varsayılan

### 4.9 Ön yüz varlıkları **yerel paketlenir**

Bootstrap, HTMX, Alpine ve Chart.js `static/vendor/` içinde saklanır; CDN
kullanılmaz.

**Neden:** Bir restoranın interneti kesildiğinde POS ekranının stilsiz kalması
kabul edilemez. Ayrıca CSP politikası `default-src 'self'` ile sıkı tutulabilir.

---

## 5. Gerçek zamanlı katman

Mutfak ekranı ve canlı sipariş akışı Django Channels ile çalışır.

```
Sipariş mutfağa gönderilir
        │
        ▼
orders.services.send_to_kitchen()
        │
        ├── KitchenTicket + TicketLine oluşturur (istasyona göre)
        ├── Reçeteye göre stok düşer
        └── kitchen.services.broadcast_ticket()
                │
                ▼
        Channel layer → grup "kitchen_<istasyon>" ve "kitchen_all"
                │
                ▼
        KitchenDisplayConsumer → tarayıcıya JSON
```

**Kanal katmanı:** Varsayılan `InMemoryChannelLayer` — tek sunucu için yeterli,
kurulum gerektirmez. Çok sunuculu dağıtımda `.env` içinde `CHANNEL_LAYER=redis`
yapılır.

**Dayanıklılık:** WebSocket bağlantısı koparsa istemci 4 saniyede bir yeniden
bağlanmayı dener; ayrıca 30 saniyelik yedek yoklama (polling) çalışır. Yayın
hatası hiçbir zaman siparişin kaydedilmesini engellemez (`try/except` ile
sarılıdır).

---

## 6. Veri modeli — temel ilişkiler

```
Category ──< Product ──< ProductVariant
                │
                ├──< Recipe ──< RecipeItem >── Ingredient
                │                                   │
                ├──> Station (kitchen)              ├──< StockBatch
                │                                   ├──< StockItem >── Warehouse
                └──< OrderItem                      └──< StockMovement
                          │
Area ──< Table ──< Order ─┤
                    │     └──< OrderItemModifier >── Modifier
                    ├──< Payment
                    ├──< OrderDiscount >── Coupon
                    ├──< Refund
                    ├──< KitchenTicket ──< TicketLine >── OrderItem
                    └──> Customer ──< LoyaltyTransaction
                                   ├──< Review
                                   └──< ConsentRecord
```

### Sipariş durum makinesi

```
DRAFT → OPEN → SENT → PREPARING → READY → SERVED → PAID
                                                 ↘
  herhangi bir aşamadan (PAID hariç) ──────────→ CANCELLED
```

Durum, KOT'ların toplu durumundan **otomatik türetilir**
(`kitchen.services._sync_order_status`): tüm KOT'lar hazırsa sipariş `READY`,
biri hazırlanıyorsa `PREPARING` olur.

---

## 7. Güvenlik katmanları

| Katman | Uygulama |
|---|---|
| Kimlik doğrulama | Kullanıcı adı **veya** e-posta; sabit zamanlı parola kontrolü |
| Brute force | django-axes — 5 deneme, 1 saat kilit (kullanıcı + IP) |
| Parola politikası | 10+ karakter, 3 karakter sınıfı, tekrar kontrolü |
| Yetkilendirme | İşlev bazlı izinler + yetkili PIN onayı |
| CSRF | Django yerleşik + `apiPost` gövdeye token ekler |
| XSS | Django şablon kaçışı + sıkı CSP |
| SQL injection | Yalnızca ORM; ham SQL kullanılmaz |
| Hız sınırlama | `RateLimitMiddleware` + DRF throttling |
| Dosya yükleme | Uzantı + boyut + **magic byte** doğrulaması |
| Güvenlik başlıkları | CSP, Permissions-Policy, nosniff, frame-ancestors none |
| Denetim | Değiştirilemez `AuditLog` |
| Gizli veri | `.env` + günlük maskeleme + alt süreç ortam temizliği |
| KVKK | PII maskeleme, rıza kaydı, anonimleştirme |

---

## 8. Performans notları

- **Veritabanı tarafı toplama:** Tüm rapor sorguları `Sum`/`Count`/`Avg` ile
  veritabanında hesaplanır.
- **`select_related` / `prefetch_related`:** Liste görünümlerinde N+1 sorgu
  önlenir.
- **İndeksler:** Sık filtrelenen alanlarda (`status`, `closed_at`,
  `remaining_quantity`, `expiry_date`) açık indeks tanımlıdır.
- **SQLite WAL:** POS yazarken mutfak ekranının okuyabilmesi için WAL modu ve
  30 saniyelik `timeout` etkindir.
- **Tutar önbelleği:** `Order.grand_total` hesaplanmış olarak saklanır.

### Bilinen ölçek sınırı

`RateLimitMiddleware` süreç içi bellek kullanır — tek süreçli kurulum için
uygundur. Çok işçili (multi-worker) dağıtımda Redis tabanlı bir çözüme
geçirilmelidir. Aynı durum `InMemoryChannelLayer` için de geçerlidir.

---

## 9. Uzatma noktaları

| Ne eklemek istiyorsanız | Nereye bakın |
|---|---|
| Yeni AI sağlayıcısı | `apps/ai/providers/` + `registry.py` |
| Yeni izin | `apps/accounts/permissions.py` → `PERMISSIONS` ve rol kümeleri |
| Yeni rapor | `apps/reports/services.py` + görünüm + şablon |
| Yeni ödeme yöntemi | `Payment.Method` + `orders/services.take_payment` |
| Yeni mutfak istasyonu | Arayüzden: **Mutfak → İstasyonlar** |
| Yeni analiz | `apps/ai/analytics.py` + `prompts.py` |
| e-Fatura entegrasyonu | `apps/reports/` — arayüz hazır, entegratör bağlanmalı |

---

## 10. Test stratejisi

| Dosya | Kapsam |
|---|---|
| `test_permissions.py` | 12 rol, izin katmanları, PIN |
| `test_orders.py` | Sipariş akışı, tutar, indirim, ödeme, iptal, iade, bölme |
| `test_inventory.py` | FIFO/FEFO, birim dönüşümü, reçete düşümü, fire |
| `test_recipes_and_costs.py` | Maliyet, marj, KDV, menü mühendisliği |
| `test_kitchen.py` | KOT ayrımı, durum geçişleri, gecikme, KOT metni |
| `test_ai.py` | Yönlendirme, yedekleme, devre kesici, bütçe, maskeleme |
| `test_security.py` | Terminal allowlist, dosya erişimi, başlıklar, KVKK |
| `test_reports_and_exports.py` | Rapor hesapları, PDF/Excel/CSV |
| `test_views_smoke.py` | 62 sayfa + detay sayfaları + REST API |

Testler **hermetiktir**: ağ erişimi yoktur, AI sağlayıcıları zorla kapatılır,
her test kendi verisini fikstürlerden kurar.
