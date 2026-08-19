"""Eğitim ilerlemesi.

Ders içeriği kaynak kodda durur (bkz. ``content.py``); burada yalnızca
kullanıcının nerede kaldığı saklanır. Ders anahtarı metin olarak tutulur:
içerikten bir ders kaldırılsa bile ilerleme kaydı hata vermez, sadece
listede görünmez.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LessonProgress(models.Model):
    """Bir kullanıcının bir dersteki durumu."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kullanıcı"),
        on_delete=models.CASCADE,
        related_name="lesson_progress",
    )
    lesson_key = models.CharField(_("ders"), max_length=60, db_index=True)
    completed_at = models.DateTimeField(_("tamamlanma"), null=True, blank=True)
    #: Sınav doğru yanıt sayısı / toplam soru
    quiz_correct = models.PositiveSmallIntegerField(_("doğru yanıt"), default=0)
    quiz_total = models.PositiveSmallIntegerField(_("soru sayısı"), default=0)
    updated_at = models.DateTimeField(_("güncellenme"), auto_now=True)

    class Meta:
        verbose_name = _("Ders ilerlemesi")
        verbose_name_plural = _("Ders ilerlemeleri")
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "lesson_key"], name="uniq_lesson_per_user")
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.lesson_key}"

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def mark_completed(self) -> None:
        if self.completed_at is None:
            self.completed_at = timezone.now()
            self.save(update_fields=["completed_at", "updated_at"])
