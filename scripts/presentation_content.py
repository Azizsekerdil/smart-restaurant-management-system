"""Tanıtım sunumunun içeriği — Türkçe ve İngilizce.

İçerik burada tek bir yerde durur; HTML, PPTX ve PDF çıktıları bundan
üretilir (bkz. ``scripts/make_presentation.py``). Böylece bir cümle
değiştiğinde beş dosyayı elle güncellemek gerekmez.

Slayt türleri
-------------
``cover``    kapak
``bullets``  başlık + madde listesi
``stats``    sayı kartları
``split``    iki sütun (sol madde, sağ vurgu kutusu)
``table``    tablo
``notice``   tam sayfa uyarı / bilgilendirme
``closing``  kapanış
``screenshot`` uygulama ekran görüntüsü (sunum/screenshots/<dil>/ altından)

Sayılar
-------
Metinlerdeki ``{{anahtar}}`` yer tutucuları, sunum üretilirken
``scripts/project_metrics.py`` ile DEPODAN ÖLÇÜLEN değerlerle doldurulur
(bkz. ``resolve_metrics``). Elle yazılmış bir sayı burada bulunmamalıdır:
elle yazılan sayı sessizce eskir ve yayımlanmış belge yanlış bilgi verir.
Ölçülemeyen bir değer için sayı UYDURULMAZ — o kart/satır sunumdan düşer.
"""

from __future__ import annotations

import re

BRAND = {
    "primary": "#1F6FEB",
    "accent": "#F97316",
    "dark": "#0B1220",
    "surface": "#111C2E",
    "text_light": "#E6EDF7",
    "muted": "#8FA3BF",
    "success": "#2EA043",
    "danger": "#DA3633",
}

META = {
    "tr": {
        "product": "Akıllı Restaurant",
        "subtitle": "Restoran Yönetim Sistemi",
        "tagline": "POS, mutfak ekranı, stok, raporlama ve yapay zekâ — tek uygulamada",
        "version": "Sürüm 1.4",
        "footer": "Akıllı Restaurant Yönetim Sistemi",
        "slide_word": "Slayt",
    },
    "en": {
        "product": "Smart Restaurant",
        "subtitle": "Restaurant Management System",
        "tagline": "POS, kitchen display, stock, reporting and AI — in one application",
        "version": "Version 1.4",
        "footer": "Smart Restaurant Management System",
        "slide_word": "Slide",
    },
}


SLIDES: list[dict] = [
    # ------------------------------------------------------------------
    {
        "kind": "cover",
        "tr": {
            "title": "Akıllı Restaurant",
            "subtitle": "Restoran Yönetim Sistemi",
            "tagline": "Siparişten mutfağa, stoktan rapora kadar restoranın tamamı tek uygulamada.",
            "chips": ["Tek dosya kurulum", "İnternetsiz çalışır", "Türkçe / İngilizce"],
        },
        "en": {
            "title": "Smart Restaurant",
            "subtitle": "Restaurant Management System",
            "tagline": "From the order to the kitchen, from stock to reports — the whole restaurant in one application.",
            "chips": ["Single-file setup", "Works offline", "Turkish / English"],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "bullets",
        "icon": "problem",
        "tr": {
            "title": "Çözdüğü sorun",
            "lead": "Çoğu restoran üç ayrı yerde çalışır: kasada bir program, mutfakta kâğıt, stokta Excel.",
            "bullets": [
                "Adisyon ile mutfak arasında kopukluk — yanlış ve geciken sipariş",
                "Stoğun ne zaman bittiğinin sipariş anında anlaşılması",
                "Reçete maliyeti bilinmediği için gerçek kârın görünmemesi",
                "Ay sonunda toplanan, karar vermeye geç kalan raporlar",
                "İptal ve indirimlerin kim tarafından yapıldığının izlenememesi",
            ],
        },
        "en": {
            "title": "The problem it solves",
            "lead": "Most restaurants run on three separate things: a till program, paper in the kitchen, and a spreadsheet for stock.",
            "bullets": [
                "A gap between the check and the kitchen — wrong and late orders",
                "Finding out an ingredient has run out only when the order is placed",
                "Real profit stays invisible because recipe cost is unknown",
                "Reports collected at month end, too late to act on",
                "No trace of who voided or discounted what",
            ],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "stats",
        "tr": {
            "title": "Sistem bir bakışta",
            "lead": "Tek bir uygulama, tek dosyalık kurulum.",
            "stats": [
                {"value": "{{modules}}", "label": "modül", "note": "POS'tan yedeklemeye"},
                {
                    "value": "{{roles}}",
                    "label": "kullanıcı rolü",
                    "note": "{{permission_codes}} ayrı yetki kodu",
                },
                {"value": "{{tests}}", "label": "otomatik test", "note": "her sürümde çalışır"},
                {"value": "2", "label": "dil", "note": "Türkçe ve İngilizce"},
            ],
        },
        "en": {
            "title": "The system at a glance",
            "lead": "One application, one single-file install.",
            "stats": [
                {"value": "{{modules}}", "label": "modules", "note": "from POS to backups"},
                {
                    "value": "{{roles}}",
                    "label": "user roles",
                    "note": "{{permission_codes}} separate permissions",
                },
                {"value": "{{tests}}", "label": "automated tests", "note": "run on every release"},
                {"value": "2", "label": "languages", "note": "Turkish and English"},
            ],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "grid",
        "tr": {
            "title": "Modüller",
            "lead": "Her modül tek başına da anlamlı; birlikte çalıştıklarında asıl değeri üretiyorlar.",
            "items": [
                {
                    "title": "POS ve sipariş",
                    "text": "Dokunmatik satış, hesap bölme, çoklu ödeme, kupon ve indirim",
                },
                {
                    "title": "Mutfak ekranı",
                    "text": "Canlı fiş akışı, istasyona göre ayırma, süre uyarıları",
                },
                {
                    "title": "Stok ve reçete",
                    "text": "Parti takibi, FIFO/FEFO, otomatik düşüm, fire kaydı",
                },
                {
                    "title": "Salon ve rezervasyon",
                    "text": "Masa planı, birleştirme, bekleme listesi",
                },
                {"title": "Müşteri ve sadakat", "text": "Segment, puan, kampanya, KVKK izinleri"},
                {"title": "Personel", "text": "Vardiya, puantaj, izin, performans"},
                {"title": "Raporlama", "text": "Satış, kârlılık, gün sonu, Excel/PDF çıktı"},
                {"title": "İstatistik merkezi", "text": "Dönem karşılaştırması, yoğunluk matrisi"},
                {"title": "Yapay zekâ", "text": "Yerel veya bulut model, akıllı analizler"},
                {"title": "Yedekleme", "text": "Tutarlı anlık görüntü, güvenli geri yükleme"},
                {"title": "Eğitim", "text": "Uygulama içi kılavuz, role göre dersler"},
                {"title": "Güvenlik", "text": "Rol bazlı yetki, denetim kaydı, PIN onayı"},
            ],
        },
        "en": {
            "title": "Modules",
            "lead": "Each module stands on its own; together they produce the real value.",
            "items": [
                {
                    "title": "POS and orders",
                    "text": "Touch sales, split checks, multiple payments, coupons and discounts",
                },
                {
                    "title": "Kitchen display",
                    "text": "Live ticket flow, split by station, time alerts",
                },
                {
                    "title": "Stock and recipes",
                    "text": "Batch tracking, FIFO/FEFO, automatic deduction, waste records",
                },
                {"title": "Floor and reservations", "text": "Table plan, merging, waiting list"},
                {
                    "title": "Customers and loyalty",
                    "text": "Segments, points, campaigns, consent records",
                },
                {"title": "Staff", "text": "Shifts, timesheets, leave, performance"},
                {
                    "title": "Reporting",
                    "text": "Sales, profitability, daily closing, Excel/PDF output",
                },
                {"title": "Statistics centre", "text": "Period comparison, intensity matrix"},
                {
                    "title": "Artificial intelligence",
                    "text": "Local or cloud model, smart analyses",
                },
                {"title": "Backups", "text": "Consistent snapshot, safe restore"},
                {"title": "Training", "text": "In-app guide, lessons by role"},
                {"title": "Security", "text": "Role-based permissions, audit log, PIN approval"},
            ],
        },
    },
    # ------------------------------------------------------------------
    #  Ekran görüntüleri — sentetik demo veriyle (seed_demo) alınmıştır;
    #  gerçek işletme/kişi verisi içermez. Yenilemek için:
    #  scripts/capture_screenshots.py
    # ------------------------------------------------------------------
    {
        "kind": "screenshot",
        "image": "01_panel.png",
        "tr": {
            "title": "Yönetim paneli",
            "caption": "Günün cirosu, sipariş sayısı, doluluk, 14 günlük eğilim, kategori dağılımı ve kritik uyarılar tek ekranda.",
        },
        "en": {
            "title": "Dashboard",
            "caption": "Today's revenue, order count, occupancy, 14-day trend, category breakdown and critical alerts on one screen.",
        },
    },
    {
        "kind": "screenshot",
        "image": "02_pos.png",
        "tr": {
            "title": "POS — satış ekranı",
            "caption": "Dokunmatik uyumlu satış: kategori filtreleri, hızlı ürün arama, adisyon ve masa yönetimi.",
        },
        "en": {
            "title": "POS — sales screen",
            "caption": "Touch-friendly selling: category filters, quick product search, check and table management.",
        },
    },
    {
        "kind": "screenshot",
        "image": "03_mutfak_kds.png",
        "tr": {
            "title": "Mutfak ekranı (KDS)",
            "caption": "Siparişler istasyona göre ayrılır, canlı akar; süre aşımında renk ve ses uyarısı verir.",
        },
        "en": {
            "title": "Kitchen display (KDS)",
            "caption": "Orders split by station and stream live; overdue tickets change colour and sound an alert.",
        },
    },
    {
        "kind": "screenshot",
        "image": "04_salon.png",
        "tr": {
            "title": "Masa planı",
            "caption": "Salon ve bölümler, masa durumları ve QR kodlu masa yönetimi tek bakışta.",
        },
        "en": {
            "title": "Table plan",
            "caption": "Floor sections, table states and QR-coded table management at a glance.",
        },
    },
    {
        "kind": "screenshot",
        "image": "05_stok.png",
        "tr": {
            "title": "Stok ve malzemeler",
            "caption": "Lot bazlı FIFO/FEFO takip, kritik seviye uyarısı ve tükenme tahmini.",
        },
        "en": {
            "title": "Stock and ingredients",
            "caption": "Lot-based FIFO/FEFO tracking, critical-level alerts and run-out forecasts.",
        },
    },
    {
        "kind": "screenshot",
        "image": "06_menu.png",
        "tr": {
            "title": "Menü ve reçeteler",
            "caption": "Ürün kartları, porsiyon ve seçenekler; reçeteden gelen gerçek maliyet ve marj.",
        },
        "en": {
            "title": "Menu and recipes",
            "caption": "Product cards, portions and modifiers; real cost and margin derived from the recipe.",
        },
    },
    {
        "kind": "screenshot",
        "image": "07_musteri.png",
        "tr": {
            "title": "Müşteri ve sadakat",
            "caption": "Segmentler, sadakat puanı, KVKK izin kayıtları ve izne bağlı maskeleme.",
        },
        "en": {
            "title": "Customers and loyalty",
            "caption": "Segments, loyalty points, consent records and permission-based masking.",
        },
    },
    {
        "kind": "screenshot",
        "image": "08_rezervasyon.png",
        "tr": {
            "title": "Rezervasyonlar",
            "caption": "Rezervasyon listesi, bekleme listesi ve çakışma kontrolü.",
        },
        "en": {
            "title": "Reservations",
            "caption": "Reservation list, waiting list and conflict checks.",
        },
    },
    {
        "kind": "screenshot",
        "image": "09_istatistik.png",
        "tr": {
            "title": "İstatistik merkezi",
            "caption": "Dönem karşılaştırması, yoğunluk matrisi ve eğilim grafikleri.",
        },
        "en": {
            "title": "Statistics centre",
            "caption": "Period comparison, intensity matrix and trend charts.",
        },
    },
    {
        "kind": "screenshot",
        "image": "10_ai_asistan.png",
        "tr": {
            "title": "Yapay zekâ asistanı",
            "caption": "Kendi verinizle soru-cevap; yerel modelde veri bilgisayardan çıkmaz.",
        },
        "en": {
            "title": "AI assistant",
            "caption": "Q&A over your own data; with a local model, nothing leaves the machine.",
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "split",
        "tr": {
            "title": "Sipariş bir kez girilir",
            "bullets": [
                "Garson POS'ta ürünü seçer, notu yazar",
                '"Mutfağa gönder" siparişi istasyonlara böler: sıcak mutfak, ızgara, bar, tatlı',
                "Aynı anda reçetedeki malzemeler stoktan düşer",
                "Mutfak ekranı fişi anında gösterir — sayfa yenilemeye gerek yok",
                "Süre aşımında fiş sarıya, sonra kırmızıya döner ve sesli uyarır",
            ],
            "highlight_title": "Neden önemli",
            "highlight_text": 'Kâğıt fiş, telefonla bağırma ve "acaba gitti mi" belirsizliği ortadan kalkar. Stok ayrı bir işlem olmaktan çıkar; satışın kendisi stoğu günceller.',
        },
        "en": {
            "title": "The order is entered once",
            "bullets": [
                "The server picks the product on the POS and adds a note",
                '"Send to kitchen" splits the order across stations: hot kitchen, grill, bar, pastry',
                "At the same moment the recipe's ingredients leave stock",
                "The kitchen screen shows the ticket instantly — no page refresh",
                "When the time is exceeded the ticket turns yellow, then red, with an audible alert",
            ],
            "highlight_title": "Why it matters",
            "highlight_text": 'Paper tickets, shouting across the pass and the "did it get through?" uncertainty disappear. Stock stops being a separate job; the sale itself updates it.',
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "split",
        "tr": {
            "title": "Gerçek kârı görmek",
            "bullets": [
                "Her ürünün reçetesi ve porsiyon verimi tanımlı",
                "Malzeme maliyeti parti bazında, gerçek alış fiyatıyla hesaplanır",
                "Kârlılık raporu ürün bazında kâr, marj ve gıda maliyet oranı verir",
                "Reçetesi olmayan ürünler ayrıca uyarı olarak listelenir",
                "Fiyat değişikliğinin marja etkisi önceden benzetilebilir",
            ],
            "highlight_title": "Dürüst rakam",
            "highlight_text": "Reçetesi tanımlanmamış bir ürünün maliyeti sıfır sayılır ve kâr olduğundan yüksek görünür. Sistem bunu gizlemez; kaç ürünün reçetesiz olduğunu raporun başında söyler.",
        },
        "en": {
            "title": "Seeing the real profit",
            "bullets": [
                "Every product has a recipe and a portion yield",
                "Ingredient cost is calculated per batch, at the real purchase price",
                "The profitability report gives profit, margin and food cost ratio per product",
                "Products without a recipe are listed separately as a warning",
                "The effect of a price change on margin can be simulated beforehand",
            ],
            "highlight_title": "An honest number",
            "highlight_text": "A product without a recipe counts as zero cost, so its profit looks higher than it is. The system does not hide this; it says at the top of the report how many products lack a recipe.",
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "split",
        "tr": {
            "title": "İstatistik merkezi",
            "bullets": [
                "Seçilen dönem, önceki eşit dönemle yan yana karşılaştırılır",
                "Gün × saat yoğunluk matrisi — personel planlaması için",
                "Müşteri davranışı: yeni / tekrar eden oranı, en değerli müşteriler",
                "Fire oranı, stok değeri, servis hızı ve masa devir hızı",
                "Tüm bölümler tek bir Excel dosyasına aktarılır",
            ],
            "highlight_title": "Az veriyle karar verilmez",
            "highlight_text": "Üç günden az gözleme dayanan hücreler soluk gösterilir. Tek bir kalabalık cumartesi, düzenli bir örüntü gibi sunulmaz — sistem hangi sayının ne kadar veriye dayandığını söyler.",
        },
        "en": {
            "title": "Statistics centre",
            "bullets": [
                "The chosen period is compared side by side with the previous equal period",
                "A day × hour intensity matrix — for staff planning",
                "Customer behaviour: new vs returning, most valuable customers",
                "Waste rate, stock value, service speed and table turnover",
                "Every section exports to a single Excel file",
            ],
            "highlight_title": "No decisions on thin data",
            "highlight_text": "Cells resting on fewer than three observations are faded. A single busy Saturday is not presented as a regular pattern — the system tells you how much data each number rests on.",
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "split",
        "tr": {
            "title": "Yapay zekâ — verinizi dışarı çıkarmadan",
            "bullets": [
                "Yerel model (LM Studio, Ollama) veya bulut sağlayıcı seçilebilir",
                "Hassas veri yalnızca yerel modele gönderilecek şekilde ayarlanabilir",
                "Müşteri kişisel verileri istem gönderilmeden önce maskelenir",
                "Talep tahmini, menü mühendisliği, fire ve anormallik analizi",
                "Günlük yönetici özeti: neyin iyi gittiği, neyin dikkat istediği",
            ],
            "highlight_title": "Tahmin, kesinlik değildir",
            "highlight_text": "Her yapay zekâ çıktısı güven düzeyi, dayandığı veri hacmi ve sınırlamalarıyla birlikte gösterilir. Bütçe sınırı konabilir; yerel modeller ücretsizdir ve bütçeye yazılmaz.",
        },
        "en": {
            "title": "AI — without your data leaving the building",
            "bullets": [
                "Choose a local model (LM Studio, Ollama) or a cloud provider",
                "Sensitive data can be restricted to the local model only",
                "Customer personal data is masked before the prompt is sent",
                "Demand forecasting, menu engineering, waste and anomaly analysis",
                "A daily management summary: what went well, what needs attention",
            ],
            "highlight_title": "A forecast is not a certainty",
            "highlight_text": "Every AI output is shown with its confidence level, the amount of data behind it and its limitations. A budget cap can be set; local models are free and are not charged against it.",
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "split",
        "tr": {
            "title": "Veri güvenliği ve yedekleme",
            "bullets": [
                "Uygulama içinden tek tıkla yedek: veritabanı, dosyalar ve taşınabilir döküm",
                "Çalışan sistemde bile tutarlı anlık görüntü alınır",
                "SHA-256 ile bütünlük doğrulaması",
                "Geri yüklemeden önce otomatik güvenlik yedeği; onay ifadesi zorunlu",
                "İsteğe bağlı otomatik zamanlanmış yedekleme",
            ],
            "highlight_title": "API anahtarları yedeğe girmez",
            "highlight_text": "Yedek arşivi çoğu zaman e-posta veya bulutla taşınır. Anahtarların bu yolla sızmaması için varsayılan olarak dışarıda bırakılır; istenirse açıkça eklenir ve arşiv işaretlenir.",
        },
        "en": {
            "title": "Data safety and backups",
            "bullets": [
                "One-click backup from inside the app: database, files and a portable dump",
                "A consistent snapshot even while the system is running",
                "Integrity verification with SHA-256",
                "An automatic safety backup before any restore; a confirmation phrase is required",
                "Optional scheduled automatic backups",
            ],
            "highlight_title": "API keys stay out of the backup",
            "highlight_text": "Backup archives usually travel by email or cloud storage. Keys are excluded by default so they cannot leak that way; they can be included explicitly, and the archive is then marked.",
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "table",
        "tr": {
            "title": "Kim neyi görür",
            "lead": "Yetki sistemi rol tabanlıdır; menüde yalnızca kullanabildiğiniz bölümler görünür.",
            "headers": ["Rol", "Görebildikleri", "Onay gerektiren"],
            "rows": [
                ["Garson", "POS, masalar, kendi siparişleri", "İptal, indirim"],
                ["Kasiyer", "POS, ödeme, kasa, temel rapor", "İade, fiyat değişimi"],
                ["Şef", "Mutfak, menü, reçete, stok", "—"],
                ["Depo", "Stok, sayım, satın alma, tedarikçi", "—"],
                ["Müdür", "Tümü + mali rapor + yedek alma", "—"],
                ["İşletme sahibi", "Tümü + geri yükleme + kullanıcılar", "—"],
            ],
        },
        "en": {
            "title": "Who sees what",
            "lead": "Permissions are role-based; the menu shows only the sections you can actually use.",
            "headers": ["Role", "What they see", "Requires approval"],
            "rows": [
                ["Server", "POS, tables, their own orders", "Voids, discounts"],
                ["Cashier", "POS, payment, till, basic reports", "Refunds, price overrides"],
                ["Chef", "Kitchen, menu, recipes, stock", "—"],
                ["Storekeeper", "Stock, counts, purchasing, suppliers", "—"],
                ["Manager", "Everything + financial reports + backups", "—"],
                ["Owner", "Everything + restore + users", "—"],
            ],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "bullets",
        "icon": "shield",
        "tr": {
            "title": "Güvenlik",
            "lead": "Restoran verisi, müşteri kişisel verisi demektir. Sistem bunu ciddiye alır.",
            "bullets": [
                "Rol bazlı yetkilendirme ve kullanıcıya özel izin ekleme/kaldırma",
                "İptal, iade, indirim gibi işlemlerde yetkili PIN onayı",
                "Değiştirilemez denetim kaydı: kim, ne zaman, neyi",
                "Beş başarısız girişte hesap kilidi",
                "Müşteri telefon ve e-postası yetkisi olmayana maskeli gösterilir",
                "KVKK kapsamında veri silme ve anonimleştirme",
            ],
        },
        "en": {
            "title": "Security",
            "lead": "Restaurant data means customer personal data. The system treats it that way.",
            "bullets": [
                "Role-based permissions, with per-user grants and revocations",
                "Manager PIN approval for voids, refunds and discounts",
                "An immutable audit log: who, when, what",
                "Account lockout after five failed sign-ins",
                "Customer phone and email are masked for users without the permission",
                "Data erasure and anonymisation for data-protection requests",
            ],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "split",
        "tr": {
            "title": "Kurulum ve kullanım",
            "bullets": [
                "Tek dosyalık Windows uygulaması (~57 MB) — Python kurulumu gerekmez",
                "Çift tıklayın; ilk açılışta örnek veriyle denemeyi teklif eder",
                "Veritabanı, dosyalar ve günlükler programın yanındaki klasörde",
                "İnternet gerekmez; bulut yapay zekâ isteğe bağlıdır",
                "Sunucu kurulumu isteyenler için PostgreSQL ve Docker desteği",
            ],
            "highlight_title": "Öğrenme yükü",
            "highlight_text": "Uygulama içinde 8 dersten oluşan bir kullanım kılavuzu var. Dersler role göre filtrelenir; garsona yedekleme dersi gösterilmez. Toplam yaklaşık 38 dakika.",
        },
        "en": {
            "title": "Setup and use",
            "bullets": [
                "A single-file Windows application (~57 MB) — no Python installation needed",
                "Double-click it; on first run it offers to try the system with demo data",
                "Database, files and logs live in the folder next to the program",
                "No internet required; cloud AI is optional",
                "PostgreSQL and Docker support for those who want a server setup",
            ],
            "highlight_title": "Learning curve",
            "highlight_text": "The application contains a built-in guide of eight lessons. Lessons are filtered by role; a server is not shown the backup lesson. About 38 minutes in total.",
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "bullets",
        "icon": "layers",
        "tr": {
            "title": "Teknik temel",
            "lead": "Uzun ömürlü, denetlenebilir ve büyüyebilir bir yapı hedeflendi.",
            "bullets": [
                "Python 3.11+ ve Django 5.2 — olgun, belgelenmiş, geniş topluluk",
                "Mutfak ekranı için WebSocket (Django Channels, Daphne)",
                "SQLite ile tek makinede; PostgreSQL ile çok terminalli kurulum",
                "{{tests}} otomatik test; her sürümde linter, biçimlendirici ve güvenlik taraması",
                "Bağımlılık açığı taraması ve gizli değer taraması yayın öncesi zorunlu",
                "Tüm ayarlar ortam değişkeninden; hiçbir gizli değer kaynak kodunda değil",
            ],
        },
        "en": {
            "title": "Technical foundation",
            "lead": "Built to last, to be auditable, and to grow.",
            "bullets": [
                "Python 3.11+ and Django 5.2 — mature, documented, widely supported",
                "WebSockets for the kitchen display (Django Channels, Daphne)",
                "SQLite on a single machine; PostgreSQL for multi-terminal setups",
                "{{tests}} automated tests; linter, formatter and security scan on every release",
                "Dependency vulnerability and secret scanning required before publishing",
                "All settings come from the environment; no secret lives in the source code",
            ],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "notice",
        "tr": {
            "title": "Mali mevzuat uyarısı",
            "text": "Sistemin ürettiği fiş, adisyon ve gün sonu raporu **işletme içi bilgilendirme amaçlıdır ve yasal mali belge yerine geçmez.**",
            "details": [
                "Yasal Z raporu, onaylı ödeme kaydedici cihaz (ÖKC / yeni nesil yazarkasa) tarafından üretilmelidir.",
                "e-Fatura ve e-Arşiv, yetkili bir özel entegratör üzerinden düzenlenmelidir.",
                "Sistem bu entegrasyonlar için arayüz hazırlığı içerir; gerçek mali belge ürettiği iddia edilmez.",
            ],
        },
        "en": {
            "title": "Fiscal compliance notice",
            "text": "The receipts, checks and daily reports this system produces are **for internal information and do not replace legal fiscal documents.**",
            "details": [
                "A legal Z report must be produced by a certified fiscal device.",
                "Electronic invoices must be issued through an authorised integrator.",
                "The system provides interfaces for these integrations; it does not claim to produce fiscal documents.",
            ],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "stats",
        "tr": {
            "title": "Kalite ölçütleri",
            "lead": "Her yayın öncesi otomatik olarak doğrulanır.",
            "stats": [
                {
                    "value": "{{tests}}",
                    "label": "test",
                    "note": "birim, entegrasyon, yetki, güvenlik",
                },
                {
                    "value": "{{dependency_scan}}",
                    "label": "bağımlılık taraması",
                    "note": "her yayın öncesi çalıştırılır",
                },
                {
                    "value": "{{translated_strings}}",
                    "label": "çevrilmiş metin",
                    "note": "Türkçe / İngilizce",
                },
                {
                    "value": "{{secret_scan}}",
                    "label": "gizli değer taraması",
                    "note": "her commit öncesi çalıştırılır",
                },
            ],
        },
        "en": {
            "title": "Quality measures",
            "lead": "Verified automatically before every release.",
            "stats": [
                {
                    "value": "{{tests}}",
                    "label": "tests",
                    "note": "unit, integration, permissions, security",
                },
                {
                    "value": "{{dependency_scan}}",
                    "label": "dependency scan",
                    "note": "run before every release",
                },
                {
                    "value": "{{translated_strings}}",
                    "label": "translated strings",
                    "note": "Turkish / English",
                },
                {
                    "value": "{{secret_scan}}",
                    "label": "secret scan",
                    "note": "run before every commit",
                },
            ],
        },
    },
    # ------------------------------------------------------------------
    {
        "kind": "closing",
        "tr": {
            "title": "Denemeye hazır",
            "lead": "Program tek dosya olarak çalışır ve ilk açılışta örnek veriyle dolu bir restoran sunar.",
            "steps": [
                "Uygulamayı boş bir klasöre koyup çift tıklayın",
                '"Örnek veriyle dene" seçeneğini işaretleyin',
                "Kurulum ekranındaki örnek veri seçeneği, kullanıcı adlarını ve o kuruluma özel rastgele bir parolayı bir kez gösterir",
                "Üst çubuktaki ? düğmesinden kullanım kılavuzuna ulaşın",
            ],
            "note": "Gerçek kullanıma geçmeden önce örnek veriyi temizleyin ve kendi kullanıcılarınızı oluşturun.",
        },
        "en": {
            "title": "Ready to try",
            "lead": "The program runs as a single file and opens with a restaurant already full of sample data.",
            "steps": [
                "Put the application in an empty folder and double-click it",
                'Choose "Try with sample data"',
                "The sample-data step prints the usernames and a one-time random password for that install",
                "Reach the user guide from the ? button in the top bar",
            ],
            "note": "Clear the sample data and create your own users before going live.",
        },
    },
]


# ======================================================================
#  ÖLÇÜLEN SAYILARIN YERLEŞTİRİLMESİ
# ======================================================================
#: Sunumda kullanılabilecek yer tutucular ve nasıl gösterilecekleri.
#: Değer ``None`` ise (ölçülemedi) o metin/kart sunumdan DÜŞER.
_TOKEN_PATTERN = re.compile(r"\{\{([a-z_]+)\}\}")


def _format_number(value: int, language: str) -> str:
    """Binlik ayracı dile göre: TR '1.764', EN '1,764'."""
    separator = "." if language == "tr" else ","
    return f"{value:,}".replace(",", separator)


def measured_values(language: str) -> dict[str, str | None]:
    """Depodan ölçülen değerler + tarama durumları, gösterim biçiminde."""
    from project_metrics import collect

    metrics = collect()
    values: dict[str, str | None] = {
        key: (None if value is None else _format_number(value, language))
        for key, value in metrics.items()
    }
    # Tarama sonuçları bir SAYI değildir; "0 açık" gibi doğrulanamaz bir
    # iddia yerine sürecin varlığı gösterilir.
    values["dependency_scan"] = "pip-audit + osv" if language == "en" else "pip-audit + osv"
    values["secret_scan"] = "gitleaks" if language == "en" else "gitleaks"
    return values


def resolve_metrics(node, language: str):
    """``{{anahtar}}`` yer tutucularını ölçülen değerlerle doldurur.

    Değeri ölçülemeyen bir yer tutucu içeren sözlük/metin **düşürülür**:
    boş ya da uydurma bir sayı yazmaktansa o kartı hiç göstermemek doğrudur.
    Fonksiyon saf çalışır; girdiyi değiştirmez.
    """
    values = measured_values(language)

    def walk(item):
        if isinstance(item, str):
            missing = [key for key in _TOKEN_PATTERN.findall(item) if values.get(key) is None]
            if missing:
                return None
            return _TOKEN_PATTERN.sub(lambda m: values[m.group(1)] or "", item)
        if isinstance(item, dict):
            result = {}
            for key, value in item.items():
                resolved = walk(value)
                if resolved is None and value is not None:
                    return None  # kartın bir parçası ölçülemedi -> kart düşer
                result[key] = resolved
            return result
        if isinstance(item, list):
            resolved_items = [walk(value) for value in item]
            return [value for value in resolved_items if value is not None]
        return item

    return walk(node)
