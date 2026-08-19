"""Çok dillilik ve eğitim modülü testleri."""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import translation

from apps.training import content
from apps.training.models import LessonProgress


# ==================================================================
#  Dil
# ==================================================================
@pytest.mark.django_db
def test_catalog_translates_model_labels():
    """Katalog derlenmiş ve yükleniyor mu?"""
    with translation.override("en"):
        assert translation.gettext("Masalar") == "Tables"
        assert translation.gettext("Mutfak") == "Kitchen"
        assert translation.gettext("sipariş türü") == "order type"

    with translation.override("tr"):
        assert translation.gettext("Masalar") == "Masalar"


@pytest.mark.django_db
def test_user_language_preference_is_applied(client, owner):
    """Profildeki dil tercihi arayüze yansımalı."""
    owner.language_preference = "en"
    owner.save(update_fields=["language_preference"])

    client.force_login(owner)
    html = client.get(reverse("reports:dashboard")).content.decode("utf-8")

    assert "Dashboard" in html
    assert "Statistics" in html


@pytest.mark.django_db
def test_switch_language_saves_to_profile(client, owner):
    client.force_login(owner)
    response = client.post(
        reverse("accounts:switch_language"),
        {"language": "en", "next": reverse("reports:dashboard")},
    )

    assert response.status_code == 302
    owner.refresh_from_db()
    assert owner.language_preference == "en"


@pytest.mark.django_db
def test_switch_language_rejects_unknown_code(client, owner):
    owner.language_preference = "tr"
    owner.save(update_fields=["language_preference"])

    client.force_login(owner)
    client.post(reverse("accounts:switch_language"), {"language": "xx"})

    owner.refresh_from_db()
    assert owner.language_preference == "tr"


@pytest.mark.django_db
def test_switch_language_blocks_open_redirect(client, owner):
    """Yönlendirme hedefi doğrulanmalı."""
    client.force_login(owner)
    response = client.post(
        reverse("accounts:switch_language"),
        {"language": "en", "next": "https://kotu-site.example/"},
    )

    assert response.status_code == 302
    assert response["Location"] == "/"


@pytest.mark.django_db
def test_anonymous_can_switch_language_on_login_page(client):
    response = client.post(
        reverse("accounts:switch_language"),
        {"language": "en", "next": reverse("accounts:login")},
    )
    assert response.status_code == 302

    html = client.get(reverse("accounts:login")).content.decode("utf-8")
    assert "Sign in" in html


@pytest.mark.django_db
def test_language_does_not_leak_between_requests(client, owner, waiter):
    """Bir kullanıcının dili diğerinin isteğine sızmamalı."""
    owner.language_preference = "en"
    owner.save(update_fields=["language_preference"])

    client.force_login(owner)
    assert "Dashboard" in client.get(reverse("reports:dashboard")).content.decode("utf-8")

    client.force_login(waiter)  # waiter tr kullanır
    html = client.get(reverse("orders:pos")).content.decode("utf-8")
    assert "Masalar" in html or "Mutfak" in html


# ==================================================================
#  Eğitim içeriği
# ==================================================================
def test_every_lesson_has_both_languages():
    """Her metin iki dilde de tanımlı olmalı."""
    for lesson in content.LESSONS.values():
        for field in (lesson.title, lesson.summary):
            assert set(field) >= {"tr", "en"}, lesson.key
            assert field["tr"] and field["en"], lesson.key

        for step in lesson.steps:
            assert set(step.title) >= {"tr", "en"}, f"{lesson.key}/{step.title}"
            assert set(step.body) >= {"tr", "en"}, f"{lesson.key}/{step.title}"
            if step.note:
                assert set(step.note) >= {"tr", "en"}, lesson.key


def test_quiz_answers_are_in_range():
    for lesson in content.LESSONS.values():
        for question in lesson.questions:
            assert 0 <= question.answer < len(question.options), lesson.key
            assert set(question.text) >= {"tr", "en"}
            for option in question.options:
                assert set(option) >= {"tr", "en"}


def test_lesson_keys_are_unique():
    keys = [lesson.key for track in content.TRACKS for lesson in track.lessons]
    assert len(keys) == len(set(keys))


def test_pick_falls_back_to_turkish():
    with translation.override("en"):
        assert content.pick({"tr": "merhaba"}) == "merhaba"
        assert content.pick({"tr": "merhaba", "en": "hello"}) == "hello"


# ==================================================================
#  Eğitim ekranları
# ==================================================================
@pytest.mark.django_db
def test_index_lists_lessons_for_owner(client, owner):
    client.force_login(owner)
    response = client.get(reverse("training:index"))

    assert response.status_code == 200
    assert response.context["total"] == len(content.LESSONS)


@pytest.mark.django_db
def test_waiter_sees_fewer_lessons(client, waiter, owner):
    """Ders listesi yetkiye göre filtrelenmeli."""
    assert len(content.visible_lessons(waiter)) < len(content.visible_lessons(owner))

    client.force_login(waiter)
    response = client.get(reverse("training:index"))
    assert response.status_code == 200

    keys = {lesson.key for lesson in content.visible_lessons(waiter)}
    assert "yedekleme" not in keys  # garsonun yedekleme yetkisi yok
    assert "pos-siparis" in keys


@pytest.mark.django_db
def test_lesson_without_permission_redirects(client, waiter):
    client.force_login(waiter)
    response = client.get(reverse("training:lesson", args=["yedekleme"]))

    assert response.status_code == 302
    assert reverse("training:index") in response["Location"]


@pytest.mark.django_db
def test_unknown_lesson_returns_404(client, owner):
    client.force_login(owner)
    assert client.get(reverse("training:lesson", args=["olmayan-ders"])).status_code == 404


@pytest.mark.django_db
def test_opening_lesson_creates_progress(client, owner):
    client.force_login(owner)
    client.get(reverse("training:lesson", args=["ilk-adimlar"]))

    record = LessonProgress.objects.get(user=owner, lesson_key="ilk-adimlar")
    assert record.completed_at is None


@pytest.mark.django_db
def test_correct_quiz_completes_lesson(client, owner):
    lesson = content.LESSONS["ilk-adimlar"]
    answers = {f"q{index}": str(q.answer) for index, q in enumerate(lesson.questions)}

    client.force_login(owner)
    response = client.post(reverse("training:complete", args=["ilk-adimlar"]), answers)

    assert response.status_code == 302
    record = LessonProgress.objects.get(user=owner, lesson_key="ilk-adimlar")
    assert record.is_completed
    assert record.quiz_correct == len(lesson.questions)


@pytest.mark.django_db
def test_wrong_quiz_does_not_complete_lesson(client, owner):
    """Yanlış yanıt varsa ders tamamlanmış sayılmamalı."""
    lesson = content.LESSONS["ilk-adimlar"]
    wrong = {
        f"q{index}": str((q.answer + 1) % len(q.options))
        for index, q in enumerate(lesson.questions)
    }

    client.force_login(owner)
    response = client.post(reverse("training:complete", args=["ilk-adimlar"]), wrong, follow=True)

    record = LessonProgress.objects.get(user=owner, lesson_key="ilk-adimlar")
    assert not record.is_completed
    assert record.quiz_correct == 0
    assert any("doğru" in str(m) for m in response.context["messages"])


@pytest.mark.django_db
def test_progress_can_be_reset(client, owner):
    client.force_login(owner)
    lesson = content.LESSONS["ilk-adimlar"]
    answers = {f"q{index}": str(q.answer) for index, q in enumerate(lesson.questions)}
    client.post(reverse("training:complete", args=["ilk-adimlar"]), answers)

    client.post(reverse("training:reset", args=["ilk-adimlar"]))
    assert not LessonProgress.objects.filter(user=owner, lesson_key="ilk-adimlar").exists()


@pytest.mark.django_db
def test_progress_percentage_reflects_completion(client, owner):
    lesson = content.LESSONS["ilk-adimlar"]
    answers = {f"q{index}": str(q.answer) for index, q in enumerate(lesson.questions)}

    client.force_login(owner)
    client.post(reverse("training:complete", args=["ilk-adimlar"]), answers)

    response = client.get(reverse("training:index"))
    assert response.context["completed"] == 1
    assert response.context["percent"] > 0


@pytest.mark.django_db
def test_lesson_renders_in_english(client, owner):
    owner.language_preference = "en"
    owner.save(update_fields=["language_preference"])

    client.force_login(owner)
    html = client.get(reverse("training:lesson", args=["pos-siparis"])).content.decode("utf-8")

    assert "Open a check" in html
    assert "Send to the kitchen" in html


@pytest.mark.django_db
def test_anonymous_cannot_open_training(client):
    response = client.get(reverse("training:index"))
    assert response.status_code == 302
    assert "login" in response["Location"]
