"""Gerçekçi demo verisi üretir.

Kullanım:
    python manage.py seed_demo                 # varsayılan: 30 günlük geçmiş
    python manage.py seed_demo --days 60       # daha uzun geçmiş
    python manage.py seed_demo --reset         # önce demo verisini temizle

Üretilen veriler gerçek bir restoranın bir aylık işleyişini taklit eder:
saat ve güne göre değişen yoğunluk, farklı ödeme yöntemleri, iptaller,
indirimler, fire kayıtları ve müşteri yorumları.
"""

from __future__ import annotations

import random
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import Role
from apps.catalog.models import (
    Allergen,
    Category,
    Modifier,
    ModifierGroup,
    Product,
    ProductVariant,
    Recipe,
    RecipeItem,
)
from apps.core.models import SystemSetting
from apps.crm.models import ConsentRecord, Customer, Review
from apps.floor.models import Area, Reservation, Table
from apps.hr.models import Attendance, Employee, Shift, ShiftAssignment, StaffTask
from apps.inventory.models import (
    Ingredient,
    IngredientCategory,
    Supplier,
    UnitOfMeasure,
    Warehouse,
    WasteRecord,
)
from apps.inventory.services import receive_stock, record_waste
from apps.kitchen.models import Station
from apps.orders.models import CashSession, Coupon, Order, OrderItem, Payment
from apps.reports.models import Expense, ExpenseCategory

User = get_user_model()
random.seed(20260815)  # tekrarlanabilir demo verisi

# ----------------------------------------------------------------------
#  SENTETİK İLETİŞİM VERİSİ
# ----------------------------------------------------------------------
#  Demo verisi hiçbir koşulda ARANABİLİR bir numara ya da ULAŞILABİLİR bir
#  e-posta adresi üretmemelidir: ekran görüntüsü, sunum veya hata kaydı
#  yoluyla dışarı çıkabilir ve gerçek bir kişiye denk gelebilir.
#
#  * Telefon "0000 " ile başlar — hiçbir ülkede geçerli bir arama öneki
#    değildir, çevrilemez.
#  * E-posta `.invalid` üst düzey alan adını kullanır; RFC 2606 ile
#    kalıcı olarak ayrılmıştır ve asla çözümlenmez.
FAKE_PHONE_PREFIX = "0000"
FAKE_EMAIL_DOMAIN = "example.invalid"


def fake_phone(index: int) -> str:
    """Aranamayan, açıkça kurgusal telefon numarası üretir."""
    return f"{FAKE_PHONE_PREFIX} 000 {index % 10000:04d}"


def fake_email(local: str) -> str:
    """Çözümlenemeyen, açıkça kurgusal e-posta adresi üretir."""
    safe = "".join(ch for ch in local.lower() if ch.isalnum() or ch in "._-") or "demo"
    return f"{safe}@{FAKE_EMAIL_DOMAIN}"


def strong_demo_pin() -> str:
    """PIN politikasına uyan (tekrar/ardışık olmayan) 4 haneli PIN üretir.

    Modülün başındaki ``random.seed(...)`` demo verisini tekrarlanabilir
    kılar — menü, satış geçmişi ve isimler için istenen budur. Ancak PIN
    bir SIRDIR: tohumlanmış üreteçten alınsaydı, kaynak kodu herkese açık
    olduğu için her kurulumdaki demo PIN'leri önceden hesaplanabilirdi.
    Bu yüzden PIN, kriptografik üreteçten (``secrets``) alınır ve kurulum
    başına farklıdır.
    """
    import secrets

    from apps.accounts.pin_security import WeakPinError, validate_pin

    while True:
        candidate = f"{secrets.randbelow(9000) + 1000}"
        try:
            validate_pin(candidate)
        except WeakPinError:
            continue
        return candidate


def generate_demo_password() -> str:
    """Kurulum başına benzersiz, güçlü bir demo parolası üretir.

    Sabit ve belgeli bir demo parolası, public bir depoda gerçek bir
    risktir: örnek veriyle açılan kurulum internete çıkarsa parola zaten
    herkesçe bilinir. Bu yüzden parola her `seed_demo` çalıştırmasında
    yeniden üretilir ve YALNIZCA komutu çalıştıran kişinin konsoluna bir
    kez yazılır.
    """
    import secrets
    import string

    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    alphabet = string.ascii_letters + string.digits
    for _attempt in range(50):
        candidate = "Demo-" + "".join(secrets.choice(alphabet) for _ in range(14))
        try:
            validate_password(candidate)
        except ValidationError:
            # Kurulumun parola politikası sıkılaştırılmış olabilir; yeni bir
            # aday üretilir. Sonsuz döngü kurulmaz.
            continue
        return candidate
    raise RuntimeError(
        "Parola politikasını karşılayan bir demo parolası üretilemedi. "
        "--password ile kendiniz bir parola verin."
    )


class Command(BaseCommand):
    help = "Gerçekçi demo verisi oluşturur (menü, stok, personel, satış geçmişi)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=30, help="Kaç günlük satış geçmişi üretilsin"
        )
        parser.add_argument("--reset", action="store_true", help="Mevcut demo verisini temizle")
        parser.add_argument(
            "--password",
            type=str,
            default="",
            help=(
                "Demo kullanıcı parolası. Boş bırakılırsa her çalıştırmada "
                "rastgele güçlü bir parola üretilir ve bir kez yazdırılır."
            ),
        )

    def handle(self, *args, **options):
        days = options["days"]
        # Sabit/belgeli demo parolası yoktur; verilmezse üretilir.
        password = options["password"] or generate_demo_password()

        if options["reset"]:
            self._reset()

        self.stdout.write(self.style.MIGRATE_HEADING("Demo verisi oluşturuluyor…"))
        units = self._units()
        self._settings()
        warehouse = self._warehouses()
        stations = self._stations()
        users = self._users(password)
        self._employees(users)
        suppliers = self._suppliers()
        ingredients = self._ingredients(units, suppliers)
        self._stock(ingredients, warehouse, suppliers)
        products = self._menu(stations, ingredients, units)
        areas, tables = self._floor()
        customers = self._customers()
        self._coupons()
        self._reservations(tables, customers)
        self._expenses()
        self._tasks(users)
        self._sales_history(days, products, tables, customers, users, warehouse, ingredients)
        self._reviews(customers)

        self.stdout.write("")
        # NOT: Bu komut paketlenmiş uygulamanın kurulum sihirbazından da
        # çalışır. Windows konsolu Türkçe kod sayfasını (cp1254/cp857)
        # kullandığı için burada yalnızca o tabloda bulunan işaretler
        # kullanılmalıdır; süslü semboller çıktıyı bozar.
        self.stdout.write(self.style.SUCCESS("[OK] Demo verisi hazir."))
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING("Demo giris bilgileri (YALNIZCA SIMDI gosterilir, kaydedin):")
        )
        for username, role in [
            ("patron", "Isletme sahibi (tum yetkiler)"),
            ("mudur", "Restoran muduru"),
            ("sef", "Sef"),
            ("garson1", "Garson"),
            ("kasiyer", "Kasiyer"),
            ("depocu", "Depo / satin alma"),
            ("muhasebe", "Muhasebe"),
        ]:
            self.stdout.write(f"  {username:<10} / {password}   -> {role}")
        issued = getattr(self, "_issued_pins", [])
        if issued:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Yetkili onayi PIN kodlari (POS iptal/indirim):"))
            for username, pin in issued:
                self.stdout.write(f"  {username:<10} PIN {pin}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "UYARI: Bu hesaplar ve tum ornek veriler SENTETIKTIR ve yalnizca\n"
                "       denemek icindir. Gercek kullanima gecmeden once ornek veriyi\n"
                "       temizleyin (--reset) ve kendi hesaplarinizi olusturun.\n"
                "       Ornek veriyle acilmis bir kurulumu internete ACMAYIN."
            )
        )
        self.stdout.write("")
        self.stdout.write("Tam yetkili yonetici icin ayrica: python manage.py createsuperuser")

    # ------------------------------------------------------------------
    def _reset(self):
        self.stdout.write(self.style.WARNING("Demo verisi temizleniyor…"))
        for model in (
            Payment,
            OrderItem,
            Order,
            CashSession,
            Review,
            ConsentRecord,
            Customer,
            Reservation,
            Table,
            Area,
            RecipeItem,
            Recipe,
            Modifier,
            ModifierGroup,
            ProductVariant,
            Product,
            Category,
            Allergen,
            WasteRecord,
            Ingredient,
            IngredientCategory,
            Supplier,
            Warehouse,
            UnitOfMeasure,
            Station,
            Attendance,
            ShiftAssignment,
            Shift,
            Employee,
            Expense,
            ExpenseCategory,
            Coupon,
            StaffTask,
        ):
            manager = getattr(model, "all_objects", model.objects)
            manager.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def _units(self) -> dict[str, UnitOfMeasure]:
        data = [
            ("g", "Gram", "mass", "1", True),
            ("kg", "Kilogram", "mass", "1000", False),
            ("ml", "Mililitre", "volume", "1", True),
            ("lt", "Litre", "volume", "1000", False),
            ("adet", "Adet", "count", "1", True),
            ("koli", "Koli (12 adet)", "count", "12", False),
            ("demet", "Demet", "count", "1", False),
        ]
        units = {}
        for code, name, dimension, factor, is_base in data:
            units[code], _ = UnitOfMeasure.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "dimension": dimension,
                    "factor_to_base": Decimal(factor),
                    "is_base": is_base,
                },
            )
        self.stdout.write(f"  · {len(units)} ölçü birimi")
        return units

    def _settings(self):
        rows = [
            (
                "loyalty_points_per_currency",
                "Sadakat: 1 ₺ = kaç puan",
                "0.10",
                "decimal",
                "sadakat",
            ),
            ("loyalty_point_value", "Sadakat: 1 puan kaç ₺", "0.10", "decimal", "sadakat"),
            ("kitchen_auto_print", "Mutfak fişini otomatik yazdır", "false", "boolean", "mutfak"),
            (
                "reservation_reminder_hours",
                "Rezervasyon hatırlatma (saat önce)",
                "3",
                "integer",
                "rezervasyon",
            ),
            ("table_cleaning_minutes", "Masa temizlik süresi (dk)", "10", "integer", "salon"),
            ("low_stock_check_enabled", "Kritik stok uyarısı", "true", "boolean", "stok"),
        ]
        for key, label, value, value_type, group in rows:
            SystemSetting.objects.get_or_create(
                key=key,
                defaults={"label": label, "value": value, "value_type": value_type, "group": group},
            )

    def _warehouses(self) -> Warehouse:
        main, _ = Warehouse.objects.get_or_create(
            code="ana", defaults={"name": "Ana Depo", "is_default": True}
        )
        Warehouse.objects.get_or_create(
            code="mutfak", defaults={"name": "Mutfak Deposu", "location": "Zemin kat"}
        )
        Warehouse.objects.get_or_create(
            code="soguk", defaults={"name": "Soğuk Oda", "is_cold_storage": True}
        )
        Warehouse.objects.get_or_create(code="bar", defaults={"name": "Bar Deposu"})
        self.stdout.write("  · 4 depo")
        return main

    def _stations(self) -> dict[str, Station]:
        data = [
            ("Sıcak Mutfak", "kitchen", "#fd7e14", 10, 20, 10),
            ("Izgara", "grill", "#dc3545", 12, 25, 20),
            ("Soğuk Mutfak", "cold", "#0dcaf0", 6, 12, 30),
            ("Bar", "bar", "#6f42c1", 4, 8, 40),
            ("Tatlı", "dessert", "#d63384", 6, 12, 50),
        ]
        stations = {}
        for name, kind, color, warning, critical, order in data:
            stations[kind], _ = Station.objects.get_or_create(
                name=name,
                defaults={
                    "kind": kind,
                    "color": color,
                    "warning_minutes": warning,
                    "critical_minutes": critical,
                    "sort_order": order,
                },
            )
        self.stdout.write(f"  · {len(stations)} istasyon")
        return stations

    def _users(self, password: str) -> dict[str, User]:
        # PIN'ler sabit DEĞİLDİR: her kurulumda politikaya uyan rastgele bir
        # PIN üretilir. Sabit demo PIN'i (1111, 2222 ...) yayımlanan bir
        # depoda yetkili onayı mekanizmasını anlamsız kılardı.
        data = [
            ("patron", "Ahmet", "Yıldız", Role.OWNER, True),
            ("gmudur", "Selin", "Kaya", Role.GENERAL_MANAGER, True),
            ("mudur", "Burak", "Demir", Role.RESTAURANT_MANAGER, True),
            ("sef", "Mehmet", "Aslan", Role.CHEF, True),
            ("asci1", "Kerem", "Doğan", Role.KITCHEN_STAFF, False),
            ("sefgarson", "Elif", "Çelik", Role.HEAD_WAITER, True),
            ("garson1", "Deniz", "Arslan", Role.WAITER, False),
            ("garson2", "Zeynep", "Koç", Role.WAITER, False),
            ("garson3", "Emre", "Şahin", Role.WAITER, False),
            ("kasiyer", "Ayşe", "Yılmaz", Role.CASHIER, True),
            ("barmen", "Can", "Öztürk", Role.BARTENDER, False),
            ("depocu", "Hakan", "Polat", Role.STOREKEEPER, False),
            ("muhasebe", "Fatma", "Erdem", Role.ACCOUNTANT, False),
            ("kurye1", "Murat", "Aydın", Role.COURIER, False),
        ]
        users = {}
        issued_pins: list[tuple[str, str]] = []
        for index, (username, first, last, role, wants_pin) in enumerate(data):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "role": role,
                    "email": fake_email(username),
                    "phone": fake_phone(index + 1),
                    "employee_code": f"P{1000 + index:04d}",
                },
            )
            if created:
                user.set_password(password)
                if wants_pin:
                    pin = strong_demo_pin()
                    user.set_pin(pin)
                    issued_pins.append((username, pin))
                user.save()
            users[username] = user
        self.stdout.write(f"  · {len(users)} kullanıcı")
        self._issued_pins = issued_pins
        return users

    def _employees(self, users: dict):
        for name, start, end in [
            ("Sabah", time(8, 0), time(16, 0)),
            ("Akşam", time(16, 0), time(0, 0)),
            ("Kapanış", time(20, 0), time(2, 0)),
        ]:
            Shift.objects.get_or_create(name=name, defaults={"start_time": start, "end_time": end})

        shifts = list(Shift.objects.all())
        for user in users.values():
            employee, _ = Employee.objects.get_or_create(
                user=user,
                defaults={
                    "hire_date": timezone.localdate() - timedelta(days=random.randint(30, 900)),
                    "hourly_rate": Decimal(random.choice(["85", "95", "110", "130"])),
                    "monthly_salary": Decimal(random.choice(["22000", "26000", "32000", "45000"])),
                },
            )
            for offset in range(-7, 8):
                work_date = timezone.localdate() + timedelta(days=offset)
                if random.random() < 0.7:
                    ShiftAssignment.objects.get_or_create(
                        employee=employee, shift=random.choice(shifts), work_date=work_date
                    )
        self.stdout.write(f"  · {Employee.objects.count()} personel kaydı ve vardiya planı")

    def _suppliers(self) -> list[Supplier]:
        data = [
            ("Anadolu Gıda Toptan", "Ali Vural", 30, 1),
            ("Ege Sebze Meyve", "Hasan Yıldırım", 7, 1),
            ("Marmara Et ve Süt", "Kemal Aktaş", 15, 2),
            ("Deniz Ürünleri A.Ş.", "Serkan Balcı", 7, 1),
            ("İçecek Dağıtım Ltd.", "Nur Aksoy", 45, 3),
        ]
        suppliers = []
        for index, (name, contact, terms, lead) in enumerate(data):
            supplier, _ = Supplier.objects.get_or_create(
                name=name,
                defaults={
                    "contact_name": contact,
                    "payment_terms_days": terms,
                    "lead_time_days": lead,
                    "rating": random.randint(3, 5),
                    # Kurgusal firma adları gerçek bir alan adına denk
                    # gelebilir; `.invalid` bunu imkânsız kılar.
                    "phone": fake_phone(2000 + index),
                    "email": fake_email(f"siparis.{name.split()[0]}"),
                },
            )
            suppliers.append(supplier)
        self.stdout.write(f"  · {len(suppliers)} tedarikçi")
        return suppliers

    def _ingredients(self, units: dict, suppliers: list) -> dict[str, Ingredient]:
        for name in [
            "Et ve Tavuk",
            "Sebze ve Meyve",
            "Süt Ürünleri",
            "Bakliyat ve Un",
            "İçecek",
            "Baharat",
            "Deniz Ürünleri",
        ]:
            IngredientCategory.objects.get_or_create(name=name)
        categories = {c.name: c for c in IngredientCategory.objects.all()}

        # (ad, kategori, temel birim, satın alma birimi, kritik seviye, bozulabilir, raf ömrü)
        data = [
            ("Dana kıyma", "Et ve Tavuk", "g", "kg", 5000, True, 3),
            ("Dana antrikot", "Et ve Tavuk", "g", "kg", 4000, True, 4),
            ("Tavuk göğsü", "Et ve Tavuk", "g", "kg", 6000, True, 3),
            ("Kuzu pirzola", "Et ve Tavuk", "g", "kg", 3000, True, 3),
            ("Somon fileto", "Deniz Ürünleri", "g", "kg", 2000, True, 2),
            ("Karides", "Deniz Ürünleri", "g", "kg", 1500, True, 2),
            ("Domates", "Sebze ve Meyve", "g", "kg", 4000, True, 5),
            ("Soğan", "Sebze ve Meyve", "g", "kg", 5000, False, 30),
            ("Marul", "Sebze ve Meyve", "g", "kg", 2000, True, 4),
            ("Patates", "Sebze ve Meyve", "g", "kg", 10000, False, 30),
            ("Biber", "Sebze ve Meyve", "g", "kg", 2000, True, 7),
            ("Limon", "Sebze ve Meyve", "adet", "adet", 30, True, 14),
            ("Beyaz peynir", "Süt Ürünleri", "g", "kg", 3000, True, 20),
            ("Kaşar peyniri", "Süt Ürünleri", "g", "kg", 3000, True, 25),
            ("Tereyağı", "Süt Ürünleri", "g", "kg", 2000, True, 30),
            ("Süt", "Süt Ürünleri", "ml", "lt", 5000, True, 5),
            ("Krema", "Süt Ürünleri", "ml", "lt", 2000, True, 10),
            ("Yumurta", "Süt Ürünleri", "adet", "adet", 60, True, 20),
            ("Un", "Bakliyat ve Un", "g", "kg", 8000, False, 180),
            ("Pirinç", "Bakliyat ve Un", "g", "kg", 6000, False, 365),
            ("Makarna", "Bakliyat ve Un", "g", "kg", 4000, False, 365),
            ("Zeytinyağı", "Baharat", "ml", "lt", 3000, False, 365),
            ("Tuz", "Baharat", "g", "kg", 2000, False, None),
            ("Karabiber", "Baharat", "g", "kg", 300, False, 365),
            ("Kekik", "Baharat", "g", "kg", 200, False, 365),
            ("Kola (33cl)", "İçecek", "adet", "koli", 48, False, 180),
            ("Su (50cl)", "İçecek", "adet", "koli", 96, False, 365),
            ("Ayran (30cl)", "İçecek", "adet", "koli", 36, True, 15),
            ("Çay", "İçecek", "g", "kg", 1000, False, 365),
            ("Kahve çekirdeği", "İçecek", "g", "kg", 1500, False, 180),
            ("Toz şeker", "Bakliyat ve Un", "g", "kg", 4000, False, 365),
            ("Çikolata", "Bakliyat ve Un", "g", "kg", 1500, False, 180),
        ]
        ingredients = {}
        for name, category, base, purchase, critical, perishable, shelf in data:
            ingredient, _ = Ingredient.objects.get_or_create(
                name=name,
                defaults={
                    "category": categories[category],
                    "base_unit": units[base],
                    "purchase_unit": units[purchase],
                    "critical_level": Decimal(critical),
                    "reorder_quantity": Decimal(critical) * 3,
                    "is_perishable": perishable,
                    "shelf_life_days": shelf,
                    "rotation": (
                        Ingredient.Rotation.FEFO if perishable else Ingredient.Rotation.FIFO
                    ),
                    "default_supplier": random.choice(suppliers),
                    "sku": f"MLZ{random.randint(1000, 9999)}",
                },
            )
            ingredients[name] = ingredient
        self.stdout.write(f"  · {len(ingredients)} malzeme")
        return ingredients

    def _stock(self, ingredients: dict, warehouse: Warehouse, suppliers: list):
        prices = {
            "Dana kıyma": "0.42",
            "Dana antrikot": "0.68",
            "Tavuk göğsü": "0.19",
            "Kuzu pirzola": "0.75",
            "Somon fileto": "0.85",
            "Karides": "0.95",
            "Domates": "0.035",
            "Soğan": "0.018",
            "Marul": "0.03",
            "Patates": "0.022",
            "Biber": "0.045",
            "Limon": "4.50",
            "Beyaz peynir": "0.24",
            "Kaşar peyniri": "0.32",
            "Tereyağı": "0.38",
            "Süt": "0.032",
            "Krema": "0.085",
            "Yumurta": "5.50",
            "Un": "0.021",
            "Pirinç": "0.055",
            "Makarna": "0.038",
            "Zeytinyağı": "0.18",
            "Tuz": "0.008",
            "Karabiber": "0.85",
            "Kekik": "0.62",
            "Kola (33cl)": "12.00",
            "Su (50cl)": "3.50",
            "Ayran (30cl)": "8.50",
            "Çay": "0.28",
            "Kahve çekirdeği": "0.72",
            "Toz şeker": "0.028",
            "Çikolata": "0.55",
        }
        for name, ingredient in ingredients.items():
            quantity = ingredient.critical_level * Decimal(str(random.uniform(2.5, 6.0)))
            receive_stock(
                ingredient,
                warehouse,
                quantity,
                Decimal(prices.get(name, "0.10")),
                movement_type="opening",
                supplier=random.choice(suppliers),
                note="Demo açılış stoğu",
                lot_code=f"LOT{random.randint(10000, 99999)}",
            )
        self.stdout.write("  · Açılış stoğu girildi")

    def _menu(self, stations: dict, ingredients: dict, units: dict) -> list[Product]:
        allergens = {}
        for code, name in [
            ("gluten", "Gluten"),
            ("sut", "Süt ürünleri"),
            ("yumurta", "Yumurta"),
            ("balik", "Balık"),
            ("kabuklu", "Kabuklu deniz ürünleri"),
            ("findik", "Sert kabuklu yemişler"),
            ("soya", "Soya"),
            ("susam", "Susam"),
            ("hardal", "Hardal"),
        ]:
            allergens[code], _ = Allergen.objects.get_or_create(code=code, defaults={"name": name})

        category_data = [
            ("Başlangıçlar", "#20c997", 10),
            ("Çorbalar", "#fd7e14", 20),
            ("Ana Yemekler", "#dc3545", 30),
            ("Izgaralar", "#b02a37", 40),
            ("Makarnalar", "#ffc107", 50),
            ("Salatalar", "#198754", 60),
            ("Tatlılar", "#d63384", 70),
            ("Sıcak İçecekler", "#6f42c1", 80),
            ("Soğuk İçecekler", "#0dcaf0", 90),
        ]
        categories = {}
        for name, color, order in category_data:
            categories[name], _ = Category.objects.get_or_create(
                name=name, defaults={"color": color, "sort_order": order}
            )

        # (ad, kategori, fiyat, KDV, hazırlık dk, istasyon, alerjenler, kalori, reçete)
        menu = [
            (
                "Mercimek Çorbası",
                "Çorbalar",
                "95",
                10,
                5,
                "kitchen",
                ["gluten"],
                180,
                [("Soğan", 30, "g"), ("Un", 10, "g"), ("Tereyağı", 15, "g"), ("Tuz", 3, "g")],
            ),
            (
                "Ezogelin Çorbası",
                "Çorbalar",
                "95",
                10,
                5,
                "kitchen",
                ["gluten"],
                195,
                [("Pirinç", 25, "g"), ("Soğan", 25, "g"), ("Tereyağı", 12, "g")],
            ),
            (
                "Humus",
                "Başlangıçlar",
                "135",
                10,
                6,
                "cold",
                ["susam"],
                220,
                [("Zeytinyağı", 20, "ml"), ("Limon", 0.25, "adet"), ("Tuz", 2, "g")],
            ),
            (
                "Sigara Böreği (6 adet)",
                "Başlangıçlar",
                "155",
                10,
                10,
                "kitchen",
                ["gluten", "sut"],
                340,
                [("Un", 80, "g"), ("Beyaz peynir", 90, "g"), ("Zeytinyağı", 25, "ml")],
            ),
            (
                "Karides Güveç",
                "Başlangıçlar",
                "395",
                10,
                14,
                "kitchen",
                ["kabuklu", "sut"],
                310,
                [
                    ("Karides", 150, "g"),
                    ("Tereyağı", 20, "g"),
                    ("Biber", 40, "g"),
                    ("Kaşar peyniri", 40, "g"),
                ],
            ),
            (
                "Adana Kebap",
                "Izgaralar",
                "445",
                10,
                18,
                "grill",
                [],
                680,
                [
                    ("Dana kıyma", 180, "g"),
                    ("Biber", 50, "g"),
                    ("Soğan", 40, "g"),
                    ("Karabiber", 2, "g"),
                ],
            ),
            (
                "Antrikot (250 g)",
                "Izgaralar",
                "780",
                10,
                20,
                "grill",
                [],
                720,
                [
                    ("Dana antrikot", 250, "g"),
                    ("Tereyağı", 15, "g"),
                    ("Tuz", 3, "g"),
                    ("Karabiber", 2, "g"),
                ],
            ),
            (
                "Kuzu Pirzola",
                "Izgaralar",
                "695",
                10,
                18,
                "grill",
                [],
                640,
                [("Kuzu pirzola", 220, "g"), ("Kekik", 2, "g"), ("Zeytinyağı", 10, "ml")],
            ),
            (
                "Izgara Tavuk",
                "Izgaralar",
                "365",
                10,
                15,
                "grill",
                [],
                420,
                [("Tavuk göğsü", 220, "g"), ("Zeytinyağı", 12, "ml"), ("Kekik", 2, "g")],
            ),
            (
                "Fırın Somon",
                "Ana Yemekler",
                "585",
                10,
                16,
                "kitchen",
                ["balik"],
                480,
                [("Somon fileto", 200, "g"), ("Limon", 0.5, "adet"), ("Zeytinyağı", 15, "ml")],
            ),
            (
                "Karnıyarık",
                "Ana Yemekler",
                "295",
                10,
                22,
                "kitchen",
                [],
                460,
                [
                    ("Dana kıyma", 120, "g"),
                    ("Domates", 80, "g"),
                    ("Biber", 40, "g"),
                    ("Soğan", 50, "g"),
                ],
            ),
            (
                "Tavuk Sote",
                "Ana Yemekler",
                "315",
                10,
                14,
                "kitchen",
                [],
                430,
                [("Tavuk göğsü", 180, "g"), ("Biber", 60, "g"), ("Domates", 70, "g")],
            ),
            (
                "Penne Arrabbiata",
                "Makarnalar",
                "265",
                10,
                12,
                "kitchen",
                ["gluten"],
                520,
                [
                    ("Makarna", 120, "g"),
                    ("Domates", 120, "g"),
                    ("Zeytinyağı", 15, "ml"),
                    ("Biber", 20, "g"),
                ],
            ),
            (
                "Fettuccine Alfredo",
                "Makarnalar",
                "295",
                10,
                12,
                "kitchen",
                ["gluten", "sut"],
                610,
                [
                    ("Makarna", 120, "g"),
                    ("Krema", 100, "ml"),
                    ("Kaşar peyniri", 40, "g"),
                    ("Tereyağı", 15, "g"),
                ],
            ),
            (
                "Sezar Salata",
                "Salatalar",
                "245",
                10,
                8,
                "cold",
                ["gluten", "sut", "yumurta"],
                320,
                [
                    ("Marul", 120, "g"),
                    ("Tavuk göğsü", 80, "g"),
                    ("Kaşar peyniri", 25, "g"),
                    ("Yumurta", 0.5, "adet"),
                ],
            ),
            (
                "Akdeniz Salata",
                "Salatalar",
                "195",
                10,
                7,
                "cold",
                ["sut"],
                260,
                [
                    ("Marul", 100, "g"),
                    ("Domates", 80, "g"),
                    ("Beyaz peynir", 50, "g"),
                    ("Zeytinyağı", 15, "ml"),
                ],
            ),
            (
                "Sufle",
                "Tatlılar",
                "175",
                10,
                12,
                "dessert",
                ["gluten", "sut", "yumurta"],
                420,
                [
                    ("Çikolata", 60, "g"),
                    ("Un", 30, "g"),
                    ("Yumurta", 1, "adet"),
                    ("Toz şeker", 40, "g"),
                ],
            ),
            (
                "Cheesecake",
                "Tatlılar",
                "185",
                10,
                5,
                "dessert",
                ["gluten", "sut", "yumurta"],
                450,
                [
                    ("Krema", 80, "ml"),
                    ("Beyaz peynir", 90, "g"),
                    ("Toz şeker", 45, "g"),
                    ("Un", 25, "g"),
                ],
            ),
            (
                "Türk Kahvesi",
                "Sıcak İçecekler",
                "85",
                10,
                5,
                "bar",
                [],
                15,
                [("Kahve çekirdeği", 12, "g"), ("Toz şeker", 5, "g")],
            ),
            ("Çay", "Sıcak İçecekler", "45", 10, 3, "bar", [], 2, [("Çay", 5, "g")]),
            (
                "Latte",
                "Sıcak İçecekler",
                "125",
                10,
                5,
                "bar",
                ["sut"],
                180,
                [("Kahve çekirdeği", 18, "g"), ("Süt", 200, "ml")],
            ),
            (
                "Kola (33 cl)",
                "Soğuk İçecekler",
                "75",
                10,
                1,
                "bar",
                [],
                139,
                [("Kola (33cl)", 1, "adet")],
            ),
            (
                "Su (50 cl)",
                "Soğuk İçecekler",
                "25",
                10,
                1,
                "bar",
                [],
                0,
                [("Su (50cl)", 1, "adet")],
            ),
            (
                "Ayran (30 cl)",
                "Soğuk İçecekler",
                "55",
                10,
                1,
                "bar",
                ["sut"],
                90,
                [("Ayran (30cl)", 1, "adet")],
            ),
            (
                "Limonata",
                "Soğuk İçecekler",
                "95",
                10,
                4,
                "bar",
                [],
                120,
                [("Limon", 1.5, "adet"), ("Toz şeker", 30, "g")],
            ),
        ]

        products = []
        for (
            name,
            category,
            price,
            tax,
            minutes,
            station,
            allergen_codes,
            calories,
            recipe_rows,
        ) in menu:
            product, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    "category": categories[category],
                    "price": Decimal(price),
                    "tax_rate": Decimal(tax),
                    "preparation_minutes": minutes,
                    "station": stations.get(station),
                    "calories": calories,
                    "sku": f"URN{random.randint(1000, 9999)}",
                    "kind": (
                        Product.Kind.DRINK
                        if "İçecek" in category
                        else (Product.Kind.DESSERT if category == "Tatlılar" else Product.Kind.FOOD)
                    ),
                    "description": f"{name} — şefimizin özel tarifiyle hazırlanır.",
                },
            )
            if created:
                product.allergens.set([allergens[c] for c in allergen_codes if c in allergens])
                recipe = Recipe.objects.create(
                    product=product,
                    labor_cost=Decimal(str(round(random.uniform(4, 18), 2))),
                    overhead_cost=Decimal(str(round(random.uniform(3, 12), 2))),
                )
                for ingredient_name, quantity, unit_code in recipe_rows:
                    if ingredient_name in ingredients:
                        RecipeItem.objects.create(
                            recipe=recipe,
                            ingredient=ingredients[ingredient_name],
                            quantity=Decimal(str(quantity)),
                            unit=units[unit_code],
                            waste_percent=Decimal(str(random.choice([0, 0, 2, 5]))),
                        )
            products.append(product)

        # Porsiyon ve ekstra seçenekleri
        for product in Product.objects.filter(category__name="Izgaralar"):
            ProductVariant.objects.get_or_create(
                product=product,
                name="Küçük",
                defaults={"price_delta": Decimal("-60"), "recipe_multiplier": Decimal("0.75")},
            )
            ProductVariant.objects.get_or_create(
                product=product,
                name="Büyük",
                defaults={"price_delta": Decimal("120"), "recipe_multiplier": Decimal("1.4")},
            )

        extras, _ = ModifierGroup.objects.get_or_create(
            name="Ekstra malzeme", defaults={"max_select": 0}
        )
        for name, delta, ingredient_name, quantity in [
            ("Ekstra peynir", "35", "Kaşar peyniri", 40),
            ("Ekstra sos", "20", "Domates", 40),
            ("Acılı", "0", None, 0),
            ("Ekstra patates", "45", "Patates", 120),
        ]:
            Modifier.objects.get_or_create(
                group=extras,
                name=name,
                defaults={
                    "price_delta": Decimal(delta),
                    "ingredient": ingredients.get(ingredient_name) if ingredient_name else None,
                    "ingredient_quantity": Decimal(str(quantity)),
                },
            )
        extras.products.set(Product.objects.exclude(category__name__contains="İçecek"))

        cooking, _ = ModifierGroup.objects.get_or_create(
            name="Pişirme derecesi",
            defaults={"is_required": True, "min_select": 1, "max_select": 1},
        )
        for name in ["Az pişmiş", "Orta", "İyi pişmiş"]:
            Modifier.objects.get_or_create(group=cooking, name=name)
        cooking.products.set(Product.objects.filter(category__name="Izgaralar"))

        self.stdout.write(f"  · {len(products)} ürün, reçeteleri ve seçenekleri")
        return products

    def _floor(self):
        area_data = [
            ("İç Salon", False, "0", 10),
            ("Teras", True, "5", 20),
            ("Bahçe", True, "5", 30),
            ("VIP Bölüm", False, "10", 40),
        ]
        areas, tables = [], []
        for name, outdoor, service, order in area_data:
            area, _ = Area.objects.get_or_create(
                name=name,
                defaults={
                    "is_outdoor": outdoor,
                    "service_charge_rate": Decimal(service),
                    "sort_order": order,
                },
            )
            areas.append(area)

            count = {"İç Salon": 12, "Teras": 8, "Bahçe": 6, "VIP Bölüm": 4}[name]
            for index in range(1, count + 1):
                prefix = {"İç Salon": "S", "Teras": "T", "Bahçe": "B", "VIP Bölüm": "V"}[name]
                table, _ = Table.objects.get_or_create(
                    area=area,
                    name=f"{prefix}{index}",
                    defaults={
                        "capacity": random.choice([2, 2, 4, 4, 4, 6, 8]),
                        "shape": random.choice(["square", "round", "rect"]),
                        "pos_x": Decimal(str(round(8 + (index - 1) % 4 * 24, 1))),
                        "pos_y": Decimal(str(round(15 + ((index - 1) // 4) * 26, 1))),
                    },
                )
                tables.append(table)
        self.stdout.write(f"  · {len(areas)} bölüm, {len(tables)} masa")
        return areas, tables

    def _customers(self) -> list[Customer]:
        first_names = [
            "Ali",
            "Ayşe",
            "Mehmet",
            "Fatma",
            "Mustafa",
            "Zeynep",
            "Emre",
            "Elif",
            "Can",
            "Deniz",
            "Burak",
            "Selin",
            "Kerem",
            "Ceren",
            "Onur",
            "Nur",
            "Yusuf",
            "Ece",
            "Barış",
            "İrem",
        ]
        last_names = [
            "Yılmaz",
            "Kaya",
            "Demir",
            "Şahin",
            "Çelik",
            "Yıldız",
            "Arslan",
            "Doğan",
            "Koç",
            "Aydın",
            "Öztürk",
            "Polat",
            "Erdem",
            "Aksoy",
            "Balcı",
        ]
        customers = []
        for index in range(60):
            first = random.choice(first_names)
            last = random.choice(last_names)
            customer = Customer.objects.create(
                first_name=first,
                last_name=last,
                phone=fake_phone(1000 + index),
                email=fake_email(f"{first}.{last}{index}"),
                allergy_notes=random.choice(
                    ["", "", "", "", "Fıstık alerjisi", "Glutensiz", "Laktoz intoleransı"]
                ),
                preferences=random.choice(
                    ["", "", "Pencere kenarı", "Sessiz masa", "Teras tercih eder"]
                ),
                company_name="" if index % 12 else f"{last} Ticaret Ltd.",
            )
            for kind in [ConsentRecord.Kind.DATA_PROCESSING, ConsentRecord.Kind.MARKETING_SMS]:
                ConsentRecord.objects.create(
                    customer=customer, kind=kind, granted=random.random() > 0.3, source="demo"
                )
            customers.append(customer)
        self.stdout.write(f"  · {len(customers)} müşteri (KVKK izinleriyle)")
        return customers

    def _coupons(self):
        Coupon.objects.get_or_create(
            code="HOSGELDIN10",
            defaults={
                "name": "Hoş geldin indirimi",
                "kind": Coupon.Kind.PERCENT,
                "value": Decimal("10"),
                "max_discount": Decimal("150"),
            },
        )
        Coupon.objects.get_or_create(
            code="OGLE50",
            defaults={
                "name": "Öğle menüsü 50 ₺ indirim",
                "kind": Coupon.Kind.AMOUNT,
                "value": Decimal("50"),
                "minimum_order_total": Decimal("300"),
            },
        )
        Coupon.objects.get_or_create(
            code="SADIK20",
            defaults={
                "name": "Sadık müşteri %20",
                "kind": Coupon.Kind.PERCENT,
                "value": Decimal("20"),
                "max_discount": Decimal("300"),
                "usage_limit_per_customer": 1,
            },
        )

    def _reservations(self, tables: list, customers: list):
        for offset in range(-5, 8):
            for _ in range(random.randint(1, 5)):
                day = timezone.localdate() + timedelta(days=offset)
                hour = random.choice([12, 13, 19, 20, 21])
                reserved_at = timezone.make_aware(
                    timezone.datetime.combine(day, time(hour, random.choice([0, 30])))
                )
                customer = random.choice(customers)
                if offset < 0:
                    status = random.choices(
                        [
                            Reservation.Status.COMPLETED,
                            Reservation.Status.NO_SHOW,
                            Reservation.Status.CANCELLED,
                        ],
                        weights=[80, 12, 8],
                    )[0]
                else:
                    status = Reservation.Status.CONFIRMED

                reservation = Reservation.objects.create(
                    customer=customer,
                    guest_name=customer.full_name,
                    guest_phone=customer.phone,
                    party_size=random.choice([2, 2, 3, 4, 4, 6]),
                    reserved_at=reserved_at,
                    status=status,
                    source=random.choice(list(Reservation.Source.values)),
                    occasion=random.choice(["", "", "", "Doğum günü", "Yıldönümü", "İş yemeği"]),
                )
                reservation.tables.set(random.sample(tables, k=random.randint(1, 2)))
        self.stdout.write(f"  · {Reservation.objects.count()} rezervasyon")

    def _expenses(self):
        for name, is_fixed in [
            ("Kira", True),
            ("Personel maaşları", True),
            ("Elektrik", False),
            ("Su", False),
            ("Doğalgaz", False),
            ("İnternet ve telefon", True),
            ("Temizlik malzemesi", False),
            ("Bakım onarım", False),
            ("Pazarlama", False),
            ("Muhasebe hizmeti", True),
        ]:
            ExpenseCategory.objects.get_or_create(name=name, defaults={"is_fixed": is_fixed})

        categories = list(ExpenseCategory.objects.all())
        for offset in range(0, 60, 3):
            category = random.choice(categories)
            Expense.objects.create(
                category=category,
                description=f"{category.name} ödemesi",
                amount=Decimal(str(round(random.uniform(500, 25000), 2))),
                tax_amount=Decimal(str(round(random.uniform(50, 2000), 2))),
                expense_date=timezone.localdate() - timedelta(days=offset),
                payment_method=random.choice(list(Expense.PaymentMethod.values)),
            )
        self.stdout.write(f"  · {Expense.objects.count()} gider kaydı")

    def _tasks(self, users: dict):
        for title, description, priority in [
            ("Açılış kontrol listesi", "Soğutucu sıcaklıkları, hijyen ve kasa kontrolü", 3),
            ("Haftalık derin temizlik", "Davlumbaz ve fritöz temizliği", 2),
            ("Stok sayımı", "Ana depo aylık sayım", 2),
            ("Menü fotoğraflarını yenile", "Yeni sezon ürünleri için çekim", 1),
            ("Kapanış kontrolü", "Gaz, elektrik, alarm ve kasa kapanışı", 3),
        ]:
            StaffTask.objects.get_or_create(
                title=title,
                defaults={
                    "description": description,
                    "priority": priority,
                    "due_date": timezone.localdate() + timedelta(days=random.randint(0, 7)),
                    "assigned_to": random.choice(list(users.values())),
                },
            )

    @transaction.atomic
    def _sales_history(self, days, products, tables, customers, users, warehouse, ingredients):
        """Gerçekçi satış geçmişi üretir: gün ve saate göre değişen yoğunluk."""
        waiters = [users[k] for k in ("garson1", "garson2", "garson3", "sefgarson")]
        cashier = users["kasiyer"]
        drinks = [p for p in products if p.category.name.endswith("İçecekler")]
        mains = [
            p for p in products if p.category.name in ("Ana Yemekler", "Izgaralar", "Makarnalar")
        ]
        starters = [
            p for p in products if p.category.name in ("Başlangıçlar", "Çorbalar", "Salatalar")
        ]
        desserts = [p for p in products if p.category.name == "Tatlılar"]

        session = CashSession.objects.create(
            terminal_name="Kasa-1", opened_by=cashier, opening_float=Decimal("2000")
        )

        total_orders = 0
        # offset 0 = bugün: panelin "bugünkü ciro" kartı boş görünmesin diye
        # bugüne de (günün ilerlemiş saatine kadar) sipariş üretilir.
        for offset in range(days, -1, -1):
            day = timezone.localdate() - timedelta(days=offset)
            weekday = day.weekday()
            # Hafta sonu daha yoğun
            base = 26 if weekday >= 4 else 16
            order_count = max(4, int(random.gauss(base, 5)))
            if offset == 0:
                # Bugün henüz bitmedi; şu ana kadarki kısmı üret.
                elapsed = max(timezone.localtime().hour - 10, 1) / 12
                order_count = max(2, int(order_count * min(elapsed, 1.0)))

            for _ in range(order_count):
                hours = [11, 12, 13, 14, 17, 18, 19, 20, 21, 22]
                weights = [4, 14, 16, 8, 6, 12, 18, 16, 10, 6]
                if offset == 0:
                    current_hour = timezone.localtime().hour
                    allowed = [
                        (h, w)
                        for h, w in zip(hours, weights, strict=False)
                        if h <= current_hour - 1
                    ]
                    if not allowed:
                        continue
                    hours, weights = [h for h, _ in allowed], [w for _, w in allowed]
                hour = random.choices(hours, weights=weights)[0]
                opened_at = timezone.make_aware(
                    timezone.datetime.combine(
                        day, time(hour, random.randint(0, 59), random.randint(0, 59))
                    )
                )
                order_type = random.choices(
                    [
                        Order.Type.DINE_IN,
                        Order.Type.TAKEAWAY,
                        Order.Type.DELIVERY,
                        Order.Type.PICKUP,
                    ],
                    weights=[70, 12, 13, 5],
                )[0]
                table = random.choice(tables) if order_type == Order.Type.DINE_IN else None
                customer = random.choice(customers) if random.random() < 0.45 else None
                guests = random.choice([1, 2, 2, 2, 3, 4, 4, 6]) if table else 1

                order = Order.objects.create(
                    order_type=order_type,
                    table=table,
                    area=table.area if table else None,
                    customer=customer,
                    waiter=random.choice(waiters),
                    cashier=cashier,
                    guest_count=guests,
                    opened_at=opened_at,
                    cash_session=session,
                    status=Order.Status.OPEN,
                )

                # Sipariş içeriği: kişi başına 1 ana + içecek, bazen başlangıç/tatlı
                lines = []
                for _guest in range(guests):
                    lines.append((random.choice(mains), 1))
                    if random.random() < 0.85:
                        lines.append((random.choice(drinks), 1))
                    if random.random() < 0.35:
                        lines.append((random.choice(starters), 1))
                    if random.random() < 0.22:
                        lines.append((random.choice(desserts), 1))

                for product, quantity in lines:
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        unit_price=product.price,
                        original_price=product.price,
                        tax_rate=product.tax_rate,
                        quantity=Decimal(quantity),
                        station=product.station,
                        status=OrderItem.Status.SERVED,
                        sent_at=opened_at + timedelta(minutes=2),
                        ready_at=opened_at + timedelta(minutes=2 + product.preparation_minutes),
                        served_at=opened_at + timedelta(minutes=4 + product.preparation_minutes),
                        stock_deducted=True,
                    )

                order.recalculate()

                # %6 iptal
                if random.random() < 0.06:
                    order.status = Order.Status.CANCELLED
                    order.cancelled_at = opened_at + timedelta(minutes=15)
                    order.cancel_reason = random.choice(
                        ["Müşteri vazgeçti", "Yanlış sipariş", "Uzun bekleme", "Ürün tükendi"]
                    )
                    order.cancelled_by = random.choice(waiters)
                    order.save()
                    continue

                # %12 indirim
                if random.random() < 0.12:
                    from apps.orders.models import OrderDiscount

                    percent = Decimal(random.choice(["5", "10", "15"]))
                    OrderDiscount.objects.create(
                        order=order,
                        kind=OrderDiscount.Kind.MANUAL,
                        label=f"Elle indirim (%{percent})",
                        percent=percent,
                        amount=(order.subtotal * percent / 100).quantize(Decimal("0.01")),
                        approved_by=users["mudur"],
                        reason="Demo indirimi",
                    )
                    order.recalculate()

                # Ödeme
                closed_at = opened_at + timedelta(minutes=random.randint(35, 110))
                method = random.choices(
                    [
                        Payment.Method.CARD,
                        Payment.Method.CASH,
                        Payment.Method.MEAL_CARD,
                        Payment.Method.ONLINE,
                    ],
                    weights=[58, 24, 12, 6],
                )[0]
                Payment.objects.create(
                    order=order,
                    method=method,
                    amount=order.grand_total,
                    received_amount=order.grand_total,
                    cashier=cashier,
                    cash_session=session,
                    paid_at=closed_at,
                )
                order.status = Order.Status.PAID
                order.closed_at = closed_at
                order.save()
                order.recalculate()

                if customer:
                    from apps.crm.services import award_loyalty_points

                    award_loyalty_points(customer, order)

                total_orders += 1

        session.counted_cash = session.expected_cash - Decimal(
            str(round(random.uniform(-40, 25), 2))
        )
        session.status = CashSession.Status.CLOSED
        session.closed_at = timezone.now() - timedelta(hours=8)
        session.closed_by = cashier
        session.save()

        # Fire kayıtları
        for _ in range(days // 2):
            ingredient = random.choice(list(ingredients.values()))
            on_hand = ingredient.total_on_hand
            if on_hand <= 0:
                continue
            # Fire miktarı mevcut stoğun küçük bir oranı olsun (negatif stok üretmemek için).
            amount = (on_hand * Decimal(str(round(random.uniform(0.005, 0.04), 4)))).quantize(
                Decimal("0.001")
            )
            if amount <= 0:
                continue
            record_waste(
                ingredient,
                warehouse,
                amount,
                random.choice(list(WasteRecord.Reason.values)),
                note="Demo fire kaydı",
            )

        self.stdout.write(f"  · {total_orders} tamamlanmış sipariş ({days} günlük geçmiş)")

    def _reviews(self, customers: list):
        comments_positive = [
            "Yemekler çok lezzetliydi, servis hızlıydı. Kesinlikle tekrar geleceğiz.",
            "Antrikot mükemmeldi. Personel çok ilgiliydi.",
            "Ortam çok keyifli, fiyatlar makul. Tavsiye ederim.",
            "Sunum harika, porsiyonlar doyurucu. Teşekkürler.",
            "Rezervasyonumuz zamanında hazırdı, hiç beklemedik.",
        ]
        comments_negative = [
            "Siparişimiz 45 dakika sonra geldi, çok bekledik.",
            "Çorba soğuktu, geri gönderdik. Servis ilgisizdi.",
            "Fiyatlar porsiyona göre yüksek geldi.",
            "Masa temizlenmemişti, uyarmak zorunda kaldık.",
            "Garson siparişi yanlış aldı, düzeltilmesi uzun sürdü.",
        ]
        comments_neutral = [
            "Yemekler normaldi, beklentimi karşıladı.",
            "Ortalama bir deneyimdi. Otopark sorunu var.",
            "Lezzet iyiydi ama bekleme süresi biraz uzundu.",
        ]

        for _ in range(70):
            rating = random.choices([5, 4, 3, 2, 1], weights=[42, 28, 15, 9, 6])[0]
            if rating >= 4:
                comment = random.choice(comments_positive)
            elif rating == 3:
                comment = random.choice(comments_neutral)
            else:
                comment = random.choice(comments_negative)

            Review.objects.create(
                customer=random.choice(customers) if random.random() < 0.8 else None,
                rating=rating,
                comment=comment,
                source=random.choice(list(Review.Source.values)),
                created_at=timezone.now() - timedelta(days=random.randint(0, 45)),
            )
        self.stdout.write(f"  · {Review.objects.count()} müşteri yorumu (AI analizi bekliyor)")
