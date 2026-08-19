"""Eğitim modülü görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.training import content
from apps.training.models import LessonProgress


def _progress_map(user) -> dict[str, LessonProgress]:
    return {item.lesson_key: item for item in LessonProgress.objects.filter(user=user)}


@login_required
def index(request):
    """Ders listesi ve genel ilerleme."""
    progress = _progress_map(request.user)
    groups = content.visible_tracks(request.user)

    for group in groups:
        group["items"] = [
            {"lesson": lesson, "progress": progress.get(lesson.key)} for lesson in group["lessons"]
        ]

    visible = content.visible_lessons(request.user)
    completed = sum(
        1 for lesson in visible if progress.get(lesson.key) and progress[lesson.key].is_completed
    )
    total_minutes = sum(lesson.minutes for lesson in visible)

    return render(
        request,
        "training/index.html",
        {
            "page_title": _("Kullanım kılavuzu"),
            "groups": groups,
            "completed": completed,
            "total": len(visible),
            "percent": round(completed / len(visible) * 100) if visible else 0,
            "total_minutes": total_minutes,
        },
    )


@login_required
def lesson(request, key: str):
    """Tek bir ders."""
    item = content.LESSONS.get(key)
    if item is None:
        raise Http404("Ders bulunamadı.")

    if item.permissions and not request.user.has_any_perm(*item.permissions):
        # Yetkisi olmayan biri için ders anlamsızdır; listeye döndür.
        messages.info(
            request,
            _("Bu ders, sizde bulunmayan bir yetkiyle ilgili olduğu için gösterilmiyor."),
        )
        return redirect("training:index")

    visible = content.visible_lessons(request.user)
    position = visible.index(item) if item in visible else -1

    record, _created = LessonProgress.objects.get_or_create(user=request.user, lesson_key=key)

    return render(
        request,
        "training/lesson.html",
        {
            "page_title": item.display_title,
            "lesson": item,
            "progress": record,
            "previous": visible[position - 1] if position > 0 else None,
            "next": visible[position + 1] if 0 <= position < len(visible) - 1 else None,
        },
    )


@require_POST
@login_required
def complete(request, key: str):
    """Dersi tamamlandı olarak işaretler; sınav varsa yanıtları değerlendirir."""
    item = content.LESSONS.get(key)
    if item is None:
        raise Http404("Ders bulunamadı.")

    record, _created = LessonProgress.objects.get_or_create(user=request.user, lesson_key=key)

    if item.questions:
        correct = 0
        for index, question in enumerate(item.questions):
            given = request.POST.get(f"q{index}")
            if given is not None and given.isdigit() and int(given) == question.answer:
                correct += 1
        record.quiz_correct = correct
        record.quiz_total = len(item.questions)
        record.save(update_fields=["quiz_correct", "quiz_total", "updated_at"])

        if correct < len(item.questions):
            # Yanlış yanıt varsa ders tamamlanmış sayılmaz: amaç rozet
            # toplamak değil, konunun anlaşılması.
            messages.warning(
                request,
                _(
                    "%(correct)s/%(total)s doğru. Yanlış yanıtların açıklamasını okuyup tekrar deneyin."
                )
                % {"correct": correct, "total": len(item.questions)},
            )
            return redirect("training:lesson", key=key)

    record.mark_completed()
    messages.success(request, _("Ders tamamlandı: %(title)s") % {"title": item.display_title})

    visible = content.visible_lessons(request.user)
    position = visible.index(item) if item in visible else -1
    if 0 <= position < len(visible) - 1:
        return redirect("training:lesson", key=visible[position + 1].key)
    return redirect("training:index")


@require_POST
@login_required
def reset(request, key: str):
    """İlerlemeyi sıfırlar."""
    LessonProgress.objects.filter(user=request.user, lesson_key=key).delete()
    messages.info(request, _("Ders ilerlemesi sıfırlandı."))
    return redirect("training:lesson", key=key)
