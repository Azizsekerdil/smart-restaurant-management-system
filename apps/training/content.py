"""Eğitim içeriği — uygulama içi kullanım kılavuzu.

İçerik neden burada
-------------------
Dersler veritabanında değil kaynak kodda tutulur. Gerekçe: içerik
uygulamanın sürümüne bağlıdır (bir ekran değişirse anlatım da değişmeli)
ve sürüm kontrolüyle birlikte ilerlemesi gerekir. Veritabanında tutulsaydı
yeni bir kuruluma taşınması ayrı bir göç işi olurdu.

Yalnızca **kullanıcının ilerlemesi** veritabanında saklanır.

Çok dillilik
------------
Uzun metinler ``.po`` kataloğuna konmaz; iki dil de burada yan yana
tutulur. Bir paragrafın çevirisini kaynağın hemen yanında görmek,
katalogda aramaktan daha güvenilirdir ve katalogu arayüz metinleri için
temiz bırakır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import get_language


def pick(texts: dict[str, str]) -> str:
    """Geçerli dile göre metni seçer, yoksa Türkçe'ye düşer."""
    language = (get_language() or "tr").split("-")[0]
    return texts.get(language) or texts.get("tr") or ""


@dataclass(frozen=True)
class Step:
    title: dict[str, str]
    body: dict[str, str]
    #: "tip" (ipucu) veya "warning" (dikkat) — arayüzde farklı renklenir
    kind: str = ""
    note: dict[str, str] = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        return pick(self.title)

    @property
    def display_body(self) -> str:
        return pick(self.body)

    @property
    def display_note(self) -> str:
        return pick(self.note)


@dataclass(frozen=True)
class Question:
    text: dict[str, str]
    options: list[dict[str, str]]
    answer: int
    explanation: dict[str, str]

    @property
    def display_text(self) -> str:
        return pick(self.text)

    @property
    def display_options(self) -> list[str]:
        return [pick(option) for option in self.options]

    @property
    def display_explanation(self) -> str:
        return pick(self.explanation)


@dataclass(frozen=True)
class Lesson:
    key: str
    title: dict[str, str]
    summary: dict[str, str]
    icon: str
    minutes: int
    #: Bu izinlerden en az birine sahip olanlara gösterilir. Boş = herkes.
    permissions: tuple[str, ...]
    steps: list[Step]
    questions: list[Question] = field(default_factory=list)
    #: İlgili ekranın URL adı — dersten doğrudan gidilebilsin diye
    target_url: str = ""

    @property
    def display_title(self) -> str:
        return pick(self.title)

    @property
    def display_summary(self) -> str:
        return pick(self.summary)


@dataclass(frozen=True)
class Track:
    key: str
    title: dict[str, str]
    description: dict[str, str]
    lessons: list[Lesson]

    @property
    def display_title(self) -> str:
        return pick(self.title)

    @property
    def display_description(self) -> str:
        return pick(self.description)


# ==================================================================
#  Dersler
# ==================================================================
_FIRST_STEPS = Lesson(
    key="ilk-adimlar",
    title={"tr": "İlk adımlar", "en": "First steps"},
    summary={
        "tr": "Giriş yapma, ekranın bölümleri, tema ve dil değiştirme.",
        "en": "Signing in, the parts of the screen, changing theme and language.",
    },
    icon="signpost",
    minutes=3,
    permissions=(),
    steps=[
        Step(
            title={"tr": "Giriş yapın", "en": "Sign in"},
            body={
                "tr": (
                    "Kullanıcı adınız ve parolanızla giriş yapın. Beş kez yanlış "
                    "parola girilirse hesap bir saat kilitlenir; bu, parola deneme "
                    "saldırılarına karşı bir korumadır. Kilitlenirseniz yöneticinize "
                    "başvurun, beklemeniz gerekmez."
                ),
                "en": (
                    "Sign in with your username and password. After five failed "
                    "attempts the account locks for one hour; this protects against "
                    "password guessing. If you get locked out, ask your manager — "
                    "you do not have to wait it out."
                ),
            },
        ),
        Step(
            title={"tr": "Ekranın bölümleri", "en": "The parts of the screen"},
            body={
                "tr": (
                    "Solda menü, üstte başlık çubuğu, ortada çalışma alanı bulunur. "
                    "Menüde yalnızca yetkiniz olan bölümler görünür; bir arkadaşınızın "
                    "ekranında olup sizde olmayan bir menü, yetki farkındandır."
                ),
                "en": (
                    "The menu is on the left, the top bar above, and the working area "
                    "in the middle. The menu only shows sections you have permission "
                    "for; if a colleague sees an item you do not, that is a difference "
                    "in permissions."
                ),
            },
        ),
        Step(
            title={"tr": "Dil ve tema", "en": "Language and theme"},
            body={
                "tr": (
                    "Üst çubuktaki çeviri simgesinden Türkçe ve İngilizce arasında "
                    "geçiş yapabilirsiniz. Seçiminiz hesabınıza kaydedilir, başka bir "
                    "cihazdan girdiğinizde de aynı dili görürsünüz. Yanındaki daire "
                    "simgesi açık/koyu temayı değiştirir."
                ),
                "en": (
                    "Use the translate icon in the top bar to switch between Turkish "
                    "and English. Your choice is saved to your account, so you see the "
                    "same language on any device. The circle icon next to it toggles "
                    "the light and dark theme."
                ),
            },
        ),
        Step(
            title={"tr": "PIN kodunuz", "en": "Your PIN"},
            body={
                "tr": (
                    "Yoğun serviste kullanıcı değiştirmek için 4-8 haneli bir PIN "
                    "tanımlayabilirsiniz. PIN, parolanızın yerine geçmez: yalnızca "
                    "hızlı geçiş ve yetkili onayı içindir."
                ),
                "en": (
                    "You can set a 4-8 digit PIN for switching users quickly during "
                    "busy service. The PIN does not replace your password: it is only "
                    "for fast switching and manager approval."
                ),
            },
            kind="tip",
            note={
                "tr": "PIN'inizi kimseyle paylaşmayın; sizin adınıza yapılan işlemler size yazılır.",
                "en": "Never share your PIN; actions taken with it are recorded under your name.",
            },
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Menüde bir bölümü göremiyorsanız bunun en olası sebebi nedir?",
                "en": "If you cannot see a section in the menu, what is the most likely reason?",
            },
            options=[
                {"tr": "O bölüm için yetkiniz yoktur", "en": "You do not have permission for it"},
                {"tr": "Sistem arızalıdır", "en": "The system is broken"},
                {"tr": "İnternet bağlantısı yoktur", "en": "There is no internet connection"},
            ],
            answer=0,
            explanation={
                "tr": "Menü, kullanıcının yetkilerine göre filtrelenir.",
                "en": "The menu is filtered according to the user's permissions.",
            },
        ),
    ],
)

_POS = Lesson(
    key="pos-siparis",
    title={"tr": "POS: sipariş alma ve ödeme", "en": "POS: taking orders and payment"},
    summary={
        "tr": "Adisyon açma, ürün ekleme, mutfağa gönderme, hesap bölme ve ödeme.",
        "en": "Opening a check, adding items, sending to the kitchen, splitting and payment.",
    },
    icon="cart3",
    minutes=6,
    permissions=("pos.use",),
    target_url="orders:pos",
    steps=[
        Step(
            title={"tr": "Adisyon açın", "en": "Open a check"},
            body={
                "tr": (
                    "POS ekranında bir masa seçin ve kişi sayısını girin. Kişi sayısı "
                    "yalnızca bilgi değildir: kişi başı ortalama ve hesap bölme "
                    "hesaplamalarında kullanılır."
                ),
                "en": (
                    "On the POS screen pick a table and enter the guest count. The "
                    "guest count is not just information: it feeds the per-guest "
                    "average and the split-check calculation."
                ),
            },
        ),
        Step(
            title={"tr": "Ürün ekleyin", "en": "Add items"},
            body={
                "tr": (
                    "Kategorilerden ürüne dokunun. Porsiyon ve ekstra seçenekleri olan "
                    "ürünlerde seçim penceresi açılır. Not alanına mutfağa iletilecek "
                    'özel istekleri yazabilirsiniz ("az pişmiş", "soğansız").'
                ),
                "en": (
                    "Tap a product in a category. Products with portions or extras open "
                    "a selection dialog. Use the note field for special requests that "
                    'should reach the kitchen ("rare", "no onion").'
                ),
            },
        ),
        Step(
            title={"tr": "Mutfağa gönderin", "en": "Send to the kitchen"},
            body={
                "tr": (
                    '"Mutfağa gönder" düğmesi siparişi hazırlık istasyonlarına böler: '
                    "sıcak mutfak, ızgara, bar ve tatlı ayrı fişler alır. Aynı anda "
                    "malzemeler reçeteye göre stoktan düşülür."
                ),
                "en": (
                    'The "Send to kitchen" button splits the order across preparation '
                    "stations: hot kitchen, grill, bar and pastry each get their own "
                    "ticket. At the same time ingredients are deducted from stock "
                    "according to the recipe."
                ),
            },
            kind="warning",
            note={
                "tr": (
                    "Gönderdikten sonra ürün silmek yetkili onayı ister ve iptal olarak "
                    "kaydedilir — çünkü ürün büyük olasılıkla hazırlanmaya başlanmıştır."
                ),
                "en": (
                    "Removing an item after sending requires manager approval and is "
                    "recorded as a void — the item has most likely already been started."
                ),
            },
        ),
        Step(
            title={"tr": "Hesabı bölün", "en": "Split the check"},
            body={
                "tr": (
                    "Üç yol vardır: eşit bölme, koltuk numarasına göre bölme ve seçili "
                    "ürünleri ayırma. Eşit bölmede kuruş farkı ilk paya eklenir, "
                    "böylece toplam hiçbir zaman tutmazlık etmez."
                ),
                "en": (
                    "There are three ways: split evenly, split by seat number, or move "
                    "selected items out. When splitting evenly the rounding remainder is "
                    "added to the first share, so the total always reconciles."
                ),
            },
        ),
        Step(
            title={"tr": "Ödeme alın", "en": "Take payment"},
            body={
                "tr": (
                    "Birden çok yöntemi aynı adisyonda kullanabilirsiniz: nakitte para "
                    "üstü otomatik hesaplanır, kalan tutar kartla kapatılabilir. Ödeme "
                    "tamamlanınca masa boşa düşer ve adisyon kapanır."
                ),
                "en": (
                    "You can combine methods on one check: cash calculates change "
                    "automatically and the remainder can be closed by card. When payment "
                    "completes the table is freed and the check is closed."
                ),
            },
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Mutfağa gönderilen bir üründe stok ne zaman düşer?",
                "en": "When is stock deducted for an item sent to the kitchen?",
            },
            options=[
                {"tr": "Mutfağa gönderildiği anda", "en": "The moment it is sent to the kitchen"},
                {"tr": "Ödeme alındığında", "en": "When payment is taken"},
                {"tr": "Gün sonunda", "en": "At end of day"},
            ],
            answer=0,
            explanation={
                "tr": "Stok, reçeteye göre mutfağa gönderim anında düşülür.",
                "en": "Stock is deducted from the recipe at the moment of sending to the kitchen.",
            },
        ),
        Question(
            text={
                "tr": "Eşit bölmede kuruş farkı ne olur?",
                "en": "What happens to the rounding remainder when splitting evenly?",
            },
            options=[
                {"tr": "İlk paya eklenir", "en": "It is added to the first share"},
                {"tr": "Silinir", "en": "It is discarded"},
                {"tr": "Bahşiş sayılır", "en": "It is counted as a tip"},
            ],
            answer=0,
            explanation={
                "tr": "Toplamın tutması için fark ilk paya eklenir.",
                "en": "The remainder goes to the first share so the total reconciles.",
            },
        ),
    ],
)

_KITCHEN = Lesson(
    key="mutfak-ekrani",
    title={"tr": "Mutfak ekranı (KDS)", "en": "Kitchen display (KDS)"},
    summary={
        "tr": "Fiş akışı, durum değiştirme, süre uyarıları ve bağlantı göstergesi.",
        "en": "Ticket flow, changing status, time alerts and the connection indicator.",
    },
    icon="fire",
    minutes=4,
    permissions=("kitchen.view",),
    target_url="kitchen:display",
    steps=[
        Step(
            title={"tr": "Fişler nasıl gelir", "en": "How tickets arrive"},
            body={
                "tr": (
                    "Ekran canlı çalışır: POS'tan gönderilen sipariş, sayfayı "
                    'yenilemeye gerek kalmadan anında belirir. Sağ üstteki "Canlı" '
                    "yazısı bağlantının açık olduğunu gösterir."
                ),
                "en": (
                    "The screen is live: an order sent from the POS appears immediately "
                    'without refreshing the page. The "Live" label in the top right '
                    "shows the connection is open."
                ),
            },
        ),
        Step(
            title={"tr": "Durum akışı", "en": "Status flow"},
            body={
                "tr": (
                    "Sırada → Hazırlanıyor → Hazır → Teslim edildi. Fişe dokunarak bir "
                    'sonraki duruma geçirirsiniz. "Hazır" olduğunda servis ekibi '
                    "bilgilendirilir."
                ),
                "en": (
                    "Queued → Preparing → Ready → Delivered. Tap a ticket to move it to "
                    'the next status. When it becomes "Ready" the service team is '
                    "notified."
                ),
            },
        ),
        Step(
            title={"tr": "Renkler ne anlatır", "en": "What the colours mean"},
            body={
                "tr": (
                    "Fiş, istasyon için tanımlanan uyarı süresini aşınca sarıya, kritik "
                    "süreyi aşınca kırmızıya döner ve sesli uyarı verir. Süreler istasyon "
                    "bazında ayarlanır; ızgara ile tatlı aynı hızda çalışmaz."
                ),
                "en": (
                    "A ticket turns yellow when it passes the station's warning time and "
                    "red with an audible alert when it passes the critical time. The "
                    "times are set per station; the grill and the pastry section do not "
                    "work at the same pace."
                ),
            },
        ),
        Step(
            title={"tr": "Bağlantı koparsa", "en": "If the connection drops"},
            body={
                "tr": (
                    '"Canlı" yazısı kaybolursa ekran otomatik olarak yeniden bağlanmayı '
                    "dener ve bu arada belirli aralıklarla sunucuyu yoklar. Sipariş kaybı "
                    "olmaz; gecikme olabilir."
                ),
                "en": (
                    'If the "Live" label disappears the screen retries the connection '
                    "automatically and polls the server in the meantime. No orders are "
                    "lost; they may simply arrive a little later."
                ),
            },
            kind="tip",
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Bir fiş kırmızıya döndüğünde ne olmuştur?",
                "en": "What has happened when a ticket turns red?",
            },
            options=[
                {
                    "tr": "Kritik hazırlık süresi aşılmıştır",
                    "en": "The critical preparation time has been exceeded",
                },
                {"tr": "Sipariş iptal edilmiştir", "en": "The order has been cancelled"},
                {"tr": "Ödeme alınmıştır", "en": "Payment has been taken"},
            ],
            answer=0,
            explanation={
                "tr": "Renk, istasyon için tanımlanan süre eşiklerine göre değişir.",
                "en": "The colour follows the time thresholds defined for the station.",
            },
        ),
    ],
)

_INVENTORY = Lesson(
    key="stok-yonetimi",
    title={"tr": "Stok ve fire", "en": "Stock and waste"},
    summary={
        "tr": "Mal kabul, parti takibi, sayım, fire kaydı ve kritik seviye uyarıları.",
        "en": "Goods receipt, batch tracking, counting, waste records and low-stock alerts.",
    },
    icon="box-seam",
    minutes=6,
    permissions=("inventory.view",),
    target_url="inventory:ingredient_list",
    steps=[
        Step(
            title={"tr": "Stok nasıl azalır", "en": "How stock decreases"},
            body={
                "tr": (
                    "Sattığınız ürünlerin reçeteleri vardır; mutfağa gönderim anında "
                    "malzemeler otomatik düşülür. Elle işlem yapmanız gerekmez. Bir "
                    "ürünün reçetesi yoksa maliyeti sıfır görünür ve kârlılık raporu "
                    "olduğundan iyi çıkar."
                ),
                "en": (
                    "The products you sell have recipes; ingredients are deducted "
                    "automatically when the order is sent to the kitchen. No manual "
                    "step is needed. If a product has no recipe its cost appears as "
                    "zero and the profitability report looks better than reality."
                ),
            },
            kind="warning",
        ),
        Step(
            title={"tr": "Parti (lot) mantığı", "en": "How batches work"},
            body={
                "tr": (
                    "Her mal kabul ayrı bir parti oluşturur ve kendi maliyetini taşır. "
                    "Tüketim FIFO (ilk giren ilk çıkar) veya FEFO (son kullanma tarihi "
                    "yakın olan önce) yöntemiyle yapılır. Bozulabilir ürünlerde FEFO "
                    "seçin."
                ),
                "en": (
                    "Every goods receipt creates a batch with its own cost. Consumption "
                    "follows FIFO (first in, first out) or FEFO (first expired, first "
                    "out). Choose FEFO for perishable items."
                ),
            },
        ),
        Step(
            title={"tr": "Fire kaydı", "en": "Recording waste"},
            body={
                "tr": (
                    "Dökülen, bozulan veya yanlış hazırlanan malzemeyi fire olarak "
                    "kaydedin. Kaydetmemek stoğu şişkin gösterir ve sayımda fark olarak "
                    "geri döner. Fire nedeni seçmek, İstatistik ekranındaki fire "
                    "analizini anlamlı kılar."
                ),
                "en": (
                    "Record spilled, spoiled or mis-prepared ingredients as waste. Not "
                    "recording it makes stock look higher than it is and shows up as a "
                    "variance at the next count. Choosing a waste reason is what makes "
                    "the waste analysis on the Statistics screen meaningful."
                ),
            },
        ),
        Step(
            title={"tr": "Sayım", "en": "Stock counting"},
            body={
                "tr": (
                    "Sayımda sistem miktarı ile saydığınız miktar yan yana gösterilir; "
                    "fark otomatik hesaplanır ve onayladığınızda düzeltme hareketi "
                    "oluşur. Sayımı servis kapalıyken yapın."
                ),
                "en": (
                    "During a count the system quantity and your counted quantity are "
                    "shown side by side; the variance is calculated automatically and "
                    "becomes an adjustment movement when you confirm. Count while "
                    "service is closed."
                ),
            },
            kind="tip",
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Reçetesi olmayan bir ürünün kârlılık raporundaki etkisi nedir?",
                "en": "What is the effect of a product without a recipe on the profitability report?",
            },
            options=[
                {"tr": "Kâr olduğundan yüksek görünür", "en": "Profit looks higher than it is"},
                {"tr": "Rapora hiç girmez", "en": "It does not appear in the report at all"},
                {"tr": "Zarar olarak görünür", "en": "It appears as a loss"},
            ],
            answer=0,
            explanation={
                "tr": "Maliyeti sıfır sayıldığı için kâr şişkin çıkar.",
                "en": "Its cost counts as zero, so the profit is inflated.",
            },
        ),
    ],
)

_STATISTICS = Lesson(
    key="istatistik-okuma",
    title={"tr": "İstatistikleri doğru okumak", "en": "Reading the statistics correctly"},
    summary={
        "tr": "Dönem karşılaştırması, gün × saat matrisi ve az veriye dayanan sonuçlar.",
        "en": "Period comparison, the day × hour matrix, and results based on little data.",
    },
    icon="bar-chart-line",
    minutes=5,
    permissions=("report.statistics",),
    target_url="reports:statistics",
    steps=[
        Step(
            title={"tr": "Karşılaştırma nasıl kurulur", "en": "How the comparison is built"},
            body={
                "tr": (
                    "Seçtiğiniz dönem, hemen önceki **eşit uzunlukta** dönemle "
                    "karşılaştırılır. Son 30 günü seçerseniz ondan önceki 30 gün taban "
                    "alınır. Yüzdeler bu tabana göre hesaplanır."
                ),
                "en": (
                    "The period you choose is compared with the immediately preceding "
                    "period of **equal length**. If you pick the last 30 days, the 30 "
                    "days before that are the baseline. Percentages are relative to it."
                ),
            },
        ),
        Step(
            title={"tr": "Gün × saat matrisi", "en": "The day × hour matrix"},
            body={
                "tr": (
                    "Hücreler toplam değil **ortalama** sipariş sayısıdır. Bir gün 30 "
                    "günlük aralıkta 4 veya 5 kez geçebilir; ham toplam bu yüzden "
                    "yanıltıcı olur. Koyu hücreler yoğun saatleri gösterir."
                ),
                "en": (
                    "Cells show the **average** number of orders, not the total. A given "
                    "weekday may occur four or five times within a 30-day range, which "
                    "makes raw totals misleading. Darker cells mark busier hours."
                ),
            },
        ),
        Step(
            title={"tr": "Soluk hücrelere dikkat", "en": "Beware of faded cells"},
            body={
                "tr": (
                    "Üç günden az gözleme dayanan hücreler soluk gösterilir. Tek bir "
                    "kalabalık cumartesi, düzenli bir örüntü gibi görünebilir. Personel "
                    "planını yalnızca koyu hücrelere dayandırın; kısa aralık seçtiyseniz "
                    "önce aralığı genişletin."
                ),
                "en": (
                    "Cells based on fewer than three observations are faded. A single "
                    "busy Saturday can look like a regular pattern. Base staffing plans "
                    "only on the solid cells; if you picked a short range, widen it first."
                ),
            },
            kind="warning",
        ),
        Step(
            title={"tr": "Tahminler kesinlik değildir", "en": "Forecasts are not certainties"},
            body={
                "tr": (
                    "Yapay zekâ üretimi tahminlerde her zaman güven düzeyi, dayandığı "
                    "veri hacmi ve sınırlamalar birlikte gösterilir. Bu alanları "
                    "okumadan bir tahmini karar dayanağı yapmayın."
                ),
                "en": (
                    "AI-generated forecasts always show a confidence level, the amount of "
                    "data behind them and their limitations. Do not base a decision on a "
                    "forecast without reading those fields."
                ),
            },
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Gün × saat matrisindeki bir hücre neyi gösterir?",
                "en": "What does a cell in the day × hour matrix show?",
            },
            options=[
                {"tr": "Ortalama sipariş sayısı", "en": "The average number of orders"},
                {"tr": "Toplam sipariş sayısı", "en": "The total number of orders"},
                {"tr": "Toplam ciro", "en": "Total revenue"},
            ],
            answer=0,
            explanation={
                "tr": "Günler aralıkta eşit sayıda geçmediği için ortalama kullanılır.",
                "en": "Averages are used because weekdays do not occur equally often in a range.",
            },
        ),
        Question(
            text={
                "tr": "Soluk gösterilen bir hücre ne anlama gelir?",
                "en": "What does a faded cell mean?",
            },
            options=[
                {"tr": "Az sayıda gözleme dayanır", "en": "It rests on very few observations"},
                {"tr": "Veri hatalıdır", "en": "The data is wrong"},
                {"tr": "O saatte kapalıydınız", "en": "You were closed at that hour"},
            ],
            answer=0,
            explanation={
                "tr": "Üç günden az gözlem güvenilir bir örüntü sayılmaz.",
                "en": "Fewer than three observations is not treated as a reliable pattern.",
            },
        ),
    ],
)

_BACKUP = Lesson(
    key="yedekleme",
    title={"tr": "Yedekleme ve geri yükleme", "en": "Backup and restore"},
    summary={
        "tr": "Yedek alma, saklama, doğrulama ve geri yüklemenin sonuçları.",
        "en": "Taking backups, storing them, verifying them, and what restoring means.",
    },
    icon="archive",
    minutes=5,
    permissions=("backup.view",),
    target_url="backups:index",
    steps=[
        Step(
            title={"tr": "Yedek neyi içerir", "en": "What a backup contains"},
            body={
                "tr": (
                    "Veritabanının tutarlı bir kopyası, yüklenen dosyalar ve taşınabilir "
                    "bir JSON dökümü. API anahtarlarınız **varsayılan olarak girmez**; "
                    "yedek çoğu zaman e-posta veya bulutla taşındığı için bu bilinçli "
                    "bir tercihtir."
                ),
                "en": (
                    "A consistent copy of the database, the uploaded files and a portable "
                    "JSON dump. Your API keys are **not included by default**; backups "
                    "often travel by email or cloud storage, so this is a deliberate "
                    "choice."
                ),
            },
        ),
        Step(
            title={"tr": "Nereye saklamalı", "en": "Where to store it"},
            body={
                "tr": (
                    "Yedekler programın yanındaki klasörde tutulur. Aynı diskteki bir "
                    "yedek disk arızasına karşı **koruma sağlamaz**. Düzenli olarak "
                    "başka bir diske veya harici belleğe kopyalayın."
                ),
                "en": (
                    "Backups are kept in a folder next to the program. A backup on the "
                    "same disk gives **no protection** against a disk failure. Copy it "
                    "regularly to another disk or an external drive."
                ),
            },
            kind="warning",
        ),
        Step(
            title={"tr": "Geri yükleme ne yapar", "en": "What restoring does"},
            body={
                "tr": (
                    "Mevcut verilerin üzerine yazar: yedek alındıktan sonra girilen her "
                    "sipariş, ödeme ve müşteri kaydı silinir. Bu yüzden sistem "
                    "işlemden hemen önce otomatik bir güvenlik yedeği alır ve onay "
                    'kutusuna "GERİ YÜKLE" yazmanızı ister.'
                ),
                "en": (
                    "It overwrites current data: every order, payment and customer record "
                    "entered after the backup is removed. That is why the system takes an "
                    "automatic safety backup immediately beforehand and asks you to type "
                    '"GERİ YÜKLE" to confirm.'
                ),
            },
            kind="warning",
        ),
        Step(
            title={"tr": "Geri yüklemeden sonra", "en": "After a restore"},
            body={
                "tr": (
                    "Kullanıcı hesapları da yedekteki hâline döndüğü için oturumunuz "
                    "kapatılır ve yeniden giriş yapmanız istenir. Yanlış bir geri "
                    "yükleme yaptıysanız, güvenlik yedeği listede durur; onu geri "
                    "yükleyerek dönebilirsiniz."
                ),
                "en": (
                    "User accounts also revert to their state in the backup, so you are "
                    "signed out and asked to sign in again. If you restored the wrong "
                    "backup, the safety backup is still in the list — restore it to come "
                    "back."
                ),
            },
            kind="tip",
        ),
        Step(
            title={
                "tr": "Test edilmemiş yedek, yedek değildir",
                "en": "An untested backup is not a backup",
            },
            body={
                "tr": (
                    "Yedeğin geri yüklenebildiğini ara ara deneyin. Ayrıntı ekranındaki "
                    '"Dosya bütünlüğü" satırı arşivin bozulmadığını gösterir, ama '
                    "gerçek güvence denemekle gelir."
                ),
                "en": (
                    "Test from time to time that a backup can actually be restored. The "
                    '"File integrity" row on the detail screen shows the archive is not '
                    "corrupted, but real confidence comes from trying it."
                ),
            },
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Geri yüklemeden hemen önce sistem ne yapar?",
                "en": "What does the system do immediately before a restore?",
            },
            options=[
                {
                    "tr": "Mevcut durumun güvenlik yedeğini alır",
                    "en": "It takes a safety backup of the current state",
                },
                {"tr": "Tüm kullanıcıları siler", "en": "It deletes all users"},
                {"tr": "Hiçbir şey", "en": "Nothing"},
            ],
            answer=0,
            explanation={
                "tr": "Güvenlik yedeği alınamazsa geri yükleme hiç başlamaz.",
                "en": "If the safety backup cannot be taken, the restore does not start at all.",
            },
        ),
    ],
)

_MANAGER = Lesson(
    key="yonetici-gunluk",
    title={"tr": "Yönetici: günlük rutin", "en": "Manager: the daily routine"},
    summary={
        "tr": "Kasa açma/kapama, gün sonu, denetim kaydı ve yetkili onayları.",
        "en": "Opening and closing the till, end of day, the audit log and manager approvals.",
    },
    icon="clipboard-check",
    minutes=5,
    permissions=("cash.manage", "report.financial"),
    target_url="reports:dashboard",
    steps=[
        Step(
            title={"tr": "Kasayı açın", "en": "Open the till"},
            body={
                "tr": (
                    "Vardiya başında açılış kasasını (bozuk para) girerek kasa oturumu "
                    "açın. Tüm nakit hareketleri bu oturuma bağlanır; oturum açılmadan "
                    "alınan nakit ödemeler gün sonunda takip edilemez."
                ),
                "en": (
                    "At the start of the shift open a till session by entering the "
                    "opening float. All cash movements attach to that session; cash taken "
                    "without an open session cannot be traced at end of day."
                ),
            },
        ),
        Step(
            title={"tr": "Yetkili onayları", "en": "Manager approvals"},
            body={
                "tr": (
                    "İptal, iade, indirim ve fiyat değiştirme gibi işlemler yetkisi "
                    "olmayan bir kullanıcı tarafından başlatıldığında yetkili PIN'i "
                    "istenir. Onaylayan kişi kayda geçer."
                ),
                "en": (
                    "When a user without the permission starts a void, refund, discount "
                    "or price override, a manager PIN is requested. Whoever approves is "
                    "recorded."
                ),
            },
        ),
        Step(
            title={"tr": "Gün sonu", "en": "End of day"},
            body={
                "tr": (
                    "Kasa kapanışında gün sonu raporu üretilir: satış, indirim, iade, "
                    "KDV, ödeme dağılımı ve kasa farkı. PDF olarak indirilebilir."
                ),
                "en": (
                    "Closing the till produces the daily report: sales, discounts, "
                    "refunds, VAT, payment breakdown and the cash variance. It can be "
                    "downloaded as a PDF."
                ),
            },
        ),
        Step(
            title={"tr": "Bu belge yasal Z raporu değildir", "en": "This is not a legal Z report"},
            body={
                "tr": (
                    "Sistemin ürettiği fiş ve gün sonu raporu işletme içi bilgilendirme "
                    "amaçlıdır. Türkiye'de yasal Z raporu onaylı ödeme kaydedici cihaz "
                    "(ÖKC) tarafından, e-Fatura ise yetkili bir özel entegratör "
                    "üzerinden üretilmelidir."
                ),
                "en": (
                    "The receipts and daily report produced by this system are for "
                    "internal information. In Türkiye a legal Z report must come from a "
                    "certified fiscal device, and e-invoices from an authorised "
                    "integrator."
                ),
            },
            kind="warning",
        ),
        Step(
            title={"tr": "Denetim kaydı", "en": "The audit log"},
            body={
                "tr": (
                    "İptal, iade, indirim, yetki değişikliği, yedekleme ve geri yükleme "
                    "gibi kritik işlemler değiştirilemez biçimde kaydedilir. Yüksek "
                    "iptal sayısı tek başına usulsüzlük kanıtı değildir; yoğun vardiya "
                    "veya operasyonel sorun da olabilir."
                ),
                "en": (
                    "Critical actions — voids, refunds, discounts, permission changes, "
                    "backups and restores — are recorded immutably. A high void count is "
                    "not proof of wrongdoing on its own; it can also mean a busy shift or "
                    "an operational problem."
                ),
            },
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Gün sonu raporu yasal Z raporu yerine geçer mi?",
                "en": "Does the daily report replace a legal Z report?",
            },
            options=[
                {
                    "tr": "Hayır, işletme içi bilgilendirmedir",
                    "en": "No, it is for internal information",
                },
                {"tr": "Evet, tamamen geçerlidir", "en": "Yes, it is fully valid"},
                {"tr": "Yalnızca nakit satışlarda geçerlidir", "en": "Only for cash sales"},
            ],
            answer=0,
            explanation={
                "tr": "Yasal Z raporu onaylı ÖKC tarafından üretilmelidir.",
                "en": "A legal Z report must be produced by a certified fiscal device.",
            },
        ),
    ],
)

_SECURITY = Lesson(
    key="guvenlik-alistkanliklari",
    title={"tr": "Güvenli kullanım alışkanlıkları", "en": "Safe working habits"},
    summary={
        "tr": "Parola, PIN, müşteri verisi ve yedeklerin gizliliği.",
        "en": "Passwords, PINs, customer data and keeping backups confidential.",
    },
    icon="shield-check",
    minutes=4,
    permissions=(),
    steps=[
        Step(
            title={"tr": "Hesabınız sizsiniz", "en": "Your account is you"},
            body={
                "tr": (
                    "Sistemdeki her işlem kullanıcı adınızla kaydedilir. Parolanızı veya "
                    "PIN'inizi paylaşmak, başkasının yaptığı işlemin size yazılması "
                    "demektir."
                ),
                "en": (
                    "Every action in the system is recorded under your username. Sharing "
                    "your password or PIN means someone else's actions are attributed to "
                    "you."
                ),
            },
        ),
        Step(
            title={"tr": "Müşteri verisi", "en": "Customer data"},
            body={
                "tr": (
                    "Telefon ve e-posta gibi bilgiler yetkisi olmayan kullanıcılara "
                    "maskeli gösterilir. Bu bilgileri dışarı çıkarmak KVKK kapsamında "
                    "sorumluluk doğurur."
                ),
                "en": (
                    "Details such as phone and email are masked for users without the "
                    "permission. Taking this data outside the system carries legal "
                    "responsibility under data protection law."
                ),
            },
        ),
        Step(
            title={"tr": "Yedekler şifrelenmemiştir", "en": "Backups are not encrypted"},
            body={
                "tr": (
                    "Yedek arşivi tüm müşteri bilgilerini ve satış geçmişini içerir. "
                    "E-posta ekiyle göndermeyin, ortak bir bulut klasörüne koymayın; "
                    "fiziksel olarak güvenli bir yerde saklayın."
                ),
                "en": (
                    "A backup archive contains all customer information and the full "
                    "sales history. Do not send it as an email attachment or drop it in a "
                    "shared cloud folder; keep it somewhere physically secure."
                ),
            },
            kind="warning",
        ),
        Step(
            title={"tr": "Ekranı kilitleyin", "en": "Lock the screen"},
            body={
                "tr": (
                    "Terminalden ayrılırken oturumu kapatın veya PIN ile kullanıcı "
                    "değiştirin. Açık bırakılan bir POS ekranı, herkesin sizin adınıza "
                    "işlem yapabilmesi demektir."
                ),
                "en": (
                    "Sign out or switch user with a PIN when you leave the terminal. A POS "
                    "screen left open means anyone can act under your name."
                ),
            },
        ),
    ],
    questions=[
        Question(
            text={
                "tr": "Yedek dosyasını e-postayla göndermek neden sakıncalıdır?",
                "en": "Why is sending a backup file by email a problem?",
            },
            options=[
                {
                    "tr": "Şifrelenmemiş müşteri verisi içerir",
                    "en": "It contains unencrypted customer data",
                },
                {"tr": "Dosya çok büyüktür", "en": "The file is too large"},
                {"tr": "Sakıncası yoktur", "en": "There is no problem"},
            ],
            answer=0,
            explanation={
                "tr": "Arşiv tüm kişisel verileri açık biçimde barındırır.",
                "en": "The archive holds all personal data in the clear.",
            },
        ),
    ],
)


TRACKS: list[Track] = [
    Track(
        key="baslangic",
        title={"tr": "Başlangıç", "en": "Getting started"},
        description={
            "tr": "Sisteme yeni başlayan herkesin okuması gereken bölüm.",
            "en": "The section everyone new to the system should read.",
        },
        lessons=[_FIRST_STEPS, _SECURITY],
    ),
    Track(
        key="servis",
        title={"tr": "Servis ve mutfak", "en": "Service and kitchen"},
        description={
            "tr": "Günlük operasyon: sipariş, mutfak akışı ve ödeme.",
            "en": "Daily operations: orders, kitchen flow and payment.",
        },
        lessons=[_POS, _KITCHEN],
    ),
    Track(
        key="yonetim",
        title={"tr": "Yönetim", "en": "Management"},
        description={
            "tr": "Stok, raporlar, istatistikler ve yedekleme.",
            "en": "Stock, reports, statistics and backups.",
        },
        lessons=[_INVENTORY, _STATISTICS, _MANAGER, _BACKUP],
    ),
]

LESSONS: dict[str, Lesson] = {lesson.key: lesson for track in TRACKS for lesson in track.lessons}


def visible_tracks(user) -> list[dict]:
    """Kullanıcının yetkisine göre filtrelenmiş ders listesi."""
    result = []
    for track in TRACKS:
        lessons = [
            lesson
            for lesson in track.lessons
            if not lesson.permissions or user.has_any_perm(*lesson.permissions)
        ]
        if lessons:
            result.append({"track": track, "lessons": lessons})
    return result


def visible_lessons(user) -> list[Lesson]:
    return [lesson for group in visible_tracks(user) for lesson in group["lessons"]]
