"""Personel, vardiya, puantaj ve görev modelleri."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.utils import money, safe_divide


class Employee(TimeStampedModel):
    """Personel özlük kaydı. Kullanıcı hesabıyla bire bir eşleşir."""

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", _("Tam zamanlı")
        PART_TIME = "part_time", _("Yarı zamanlı")
        HOURLY = "hourly", _("Saatlik")
        SEASONAL = "seasonal", _("Sezonluk")
        INTERN = "intern", _("Stajyer")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kullanıcı"),
        on_delete=models.CASCADE,
        related_name="employee",
    )
    employment_type = models.CharField(
        _("çalışma şekli"),
        max_length=12,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    hire_date = models.DateField(_("işe giriş"), default=date.today)
    termination_date = models.DateField(_("işten ayrılış"), null=True, blank=True)

    hourly_rate = models.DecimalField(
        _("saatlik ücret"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    monthly_salary = models.DecimalField(
        _("aylık ücret"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    weekly_hours_target = models.PositiveSmallIntegerField(_("haftalık hedef saat"), default=45)

    emergency_contact = models.CharField(_("acil durum kişisi"), max_length=120, blank=True)
    emergency_phone = models.CharField(_("acil durum telefonu"), max_length=20, blank=True)
    notes = models.TextField(_("notlar"), blank=True)
    is_active = models.BooleanField(_("aktif"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Personel")
        verbose_name_plural = _("Personel")
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self) -> str:
        return self.user.display_name

    @property
    def tenure_days(self) -> int:
        end = self.termination_date or timezone.localdate()
        return (end - self.hire_date).days

    def hours_worked(self, start: date, end: date) -> Decimal:
        records = self.attendances.filter(
            check_in__date__gte=start, check_in__date__lte=end, check_out__isnull=False
        )
        total = sum((r.worked_hours for r in records), Decimal("0"))
        return Decimal(total).quantize(Decimal("0.01"))

    def sales_total(self, start: date, end: date) -> Decimal:
        """Bu personelin garson olarak kapattığı satış toplamı."""
        from apps.orders.models import Order

        total = Order.objects.filter(
            waiter=self.user,
            status=Order.Status.PAID,
            closed_at__date__gte=start,
            closed_at__date__lte=end,
        ).aggregate(t=models.Sum("grand_total"))["t"]
        return money(total or 0)


class Shift(TimeStampedModel):
    """Vardiya tanımı (sabah, akşam, kapanış)."""

    name = models.CharField(_("ad"), max_length=80, unique=True)
    start_time = models.TimeField(_("başlangıç"))
    end_time = models.TimeField(_("bitiş"))
    color = models.CharField(_("renk"), max_length=7, default="#6f42c1")
    break_minutes = models.PositiveSmallIntegerField(_("mola (dk)"), default=30)
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Vardiya")
        verbose_name_plural = _("Vardiyalar")
        ordering = ["start_time"]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"

    @property
    def duration_hours(self) -> Decimal:
        start = datetime.combine(date.today(), self.start_time)
        end = datetime.combine(date.today(), self.end_time)
        if end <= start:
            end += timedelta(days=1)
        hours = Decimal((end - start).total_seconds()) / Decimal("3600")
        return (hours - Decimal(self.break_minutes) / Decimal("60")).quantize(Decimal("0.01"))


class ShiftAssignment(TimeStampedModel):
    """Personelin belirli bir gündeki vardiya ataması."""

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planlandı")
        CONFIRMED = "confirmed", _("Onaylandı")
        COMPLETED = "completed", _("Tamamlandı")
        ABSENT = "absent", _("Gelmedi")
        SWAPPED = "swapped", _("Değiştirildi")

    employee = models.ForeignKey(
        Employee,
        verbose_name=_("personel"),
        on_delete=models.CASCADE,
        related_name="shift_assignments",
    )
    shift = models.ForeignKey(
        Shift, verbose_name=_("vardiya"), on_delete=models.PROTECT, related_name="assignments"
    )
    work_date = models.DateField(_("tarih"), db_index=True)
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.PLANNED
    )
    role_note = models.CharField(_("görev notu"), max_length=200, blank=True)
    is_ai_suggested = models.BooleanField(_("AI önerisi"), default=False)

    class Meta:
        verbose_name = _("Vardiya ataması")
        verbose_name_plural = _("Vardiya atamaları")
        ordering = ["work_date", "shift__start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "work_date", "shift"], name="uniq_shift_per_employee_day"
            )
        ]
        indexes = [models.Index(fields=["work_date", "status"])]

    def __str__(self) -> str:
        return f"{self.employee} · {self.work_date} · {self.shift.name}"


class Attendance(TimeStampedModel):
    """Giriş / çıkış kaydı (puantaj)."""

    employee = models.ForeignKey(
        Employee, verbose_name=_("personel"), on_delete=models.CASCADE, related_name="attendances"
    )
    check_in = models.DateTimeField(_("giriş"), default=timezone.now, db_index=True)
    check_out = models.DateTimeField(_("çıkış"), null=True, blank=True)
    break_minutes = models.PositiveSmallIntegerField(_("mola (dk)"), default=0)
    assignment = models.ForeignKey(
        ShiftAssignment,
        verbose_name=_("vardiya ataması"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendances",
    )
    note = models.CharField(_("not"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Puantaj kaydı")
        verbose_name_plural = _("Puantaj kayıtları")
        ordering = ["-check_in"]

    def __str__(self) -> str:
        return f"{self.employee} · {timezone.localtime(self.check_in):%d.%m %H:%M}"

    @property
    def worked_hours(self) -> Decimal:
        if not self.check_out:
            return Decimal("0.00")
        seconds = (self.check_out - self.check_in).total_seconds()
        hours = Decimal(seconds) / Decimal("3600") - Decimal(self.break_minutes) / Decimal("60")
        return max(hours, Decimal("0")).quantize(Decimal("0.01"))

    @property
    def is_open(self) -> bool:
        return self.check_out is None

    @property
    def is_late(self) -> bool:
        """Planlanan vardiya başlangıcından 10 dk sonra giriş yaptıysa geç sayılır."""
        if not self.assignment_id:
            return False
        planned = timezone.make_aware(
            datetime.combine(self.assignment.work_date, self.assignment.shift.start_time)
        )
        return self.check_in > planned + timedelta(minutes=10)


class LeaveRequest(TimeStampedModel):
    """İzin talebi."""

    class Kind(models.TextChoices):
        ANNUAL = "annual", _("Yıllık izin")
        SICK = "sick", _("Hastalık izni")
        UNPAID = "unpaid", _("Ücretsiz izin")
        MATERNITY = "maternity", _("Doğum izni")
        OTHER = "other", _("Diğer")

    class Status(models.TextChoices):
        PENDING = "pending", _("Onay bekliyor")
        APPROVED = "approved", _("Onaylandı")
        REJECTED = "rejected", _("Reddedildi")
        CANCELLED = "cancelled", _("İptal")

    employee = models.ForeignKey(
        Employee,
        verbose_name=_("personel"),
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    kind = models.CharField(
        _("izin türü"), max_length=10, choices=Kind.choices, default=Kind.ANNUAL
    )
    start_date = models.DateField(_("başlangıç"))
    end_date = models.DateField(_("bitiş"))
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reason = models.TextField(_("gerekçe"), blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("karar veren"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_leaves",
    )
    decided_at = models.DateTimeField(_("karar zamanı"), null=True, blank=True)
    decision_note = models.CharField(_("karar notu"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("İzin talebi")
        verbose_name_plural = _("İzin talepleri")
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.employee} · {self.start_date} - {self.end_date}"

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


class StaffTask(TimeStampedModel):
    """Görev listesi (açılış kontrolü, temizlik, kapanış)."""

    class Status(models.TextChoices):
        OPEN = "open", _("Açık")
        IN_PROGRESS = "in_progress", _("Devam ediyor")
        DONE = "done", _("Tamamlandı")
        SKIPPED = "skipped", _("Atlandı")

    class Priority(models.IntegerChoices):
        LOW = 1, _("Düşük")
        NORMAL = 2, _("Normal")
        HIGH = 3, _("Yüksek")

    title = models.CharField(_("başlık"), max_length=200)
    description = models.TextField(_("açıklama"), blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("atanan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
    )
    target_roles = models.JSONField(_("hedef roller"), default=list, blank=True)
    due_date = models.DateField(_("son tarih"), null=True, blank=True, db_index=True)
    status = models.CharField(
        _("durum"), max_length=12, choices=Status.choices, default=Status.OPEN
    )
    priority = models.PositiveSmallIntegerField(
        _("öncelik"), choices=Priority.choices, default=Priority.NORMAL
    )
    is_recurring = models.BooleanField(_("tekrarlayan"), default=False)
    completed_at = models.DateTimeField(_("tamamlanma"), null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("tamamlayan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_tasks",
    )

    class Meta:
        verbose_name = _("Görev")
        verbose_name_plural = _("Görevler")
        ordering = ["-priority", "due_date"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_date
            and self.due_date < timezone.localdate()
            and self.status not in {self.Status.DONE, self.Status.SKIPPED}
        )


class PerformanceSnapshot(TimeStampedModel):
    """Dönemsel personel performans özeti (rapor ve AI analizi için)."""

    employee = models.ForeignKey(
        Employee, verbose_name=_("personel"), on_delete=models.CASCADE, related_name="performance"
    )
    period_start = models.DateField(_("dönem başı"))
    period_end = models.DateField(_("dönem sonu"))
    orders_served = models.PositiveIntegerField(_("servis edilen sipariş"), default=0)
    sales_total = models.DecimalField(
        _("satış toplamı"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    average_ticket = models.DecimalField(
        _("ortalama adisyon"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    hours_worked = models.DecimalField(
        _("çalışılan saat"), max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    void_count = models.PositiveIntegerField(_("iptal sayısı"), default=0)
    discount_total = models.DecimalField(
        _("verilen indirim"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    late_count = models.PositiveIntegerField(_("geç kalma"), default=0)

    class Meta:
        verbose_name = _("Performans özeti")
        verbose_name_plural = _("Performans özetleri")
        ordering = ["-period_end"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "period_start", "period_end"], name="uniq_performance_period"
            )
        ]

    def __str__(self) -> str:
        return f"{self.employee} · {self.period_start} - {self.period_end}"

    @property
    def sales_per_hour(self) -> Decimal:
        return money(safe_divide(self.sales_total, self.hours_worked or 1))


def default_shifts() -> list[tuple[str, time, time]]:
    """Demo veri ve ilk kurulum için örnek vardiyalar."""
    return [
        ("Sabah", time(8, 0), time(16, 0)),
        ("Akşam", time(16, 0), time(0, 0)),
        ("Kapanış", time(20, 0), time(2, 0)),
    ]
