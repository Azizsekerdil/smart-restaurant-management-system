"""Celery uygulaması (isteğe bağlı).

CELERY_ENABLED=False iken görevler `task_always_eager` ile senkron
çalışır; böylece Redis kurulumu olmadan da sistem tam işlevlidir.
"""

from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    from celery import Celery

    app = Celery("restaurant")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()
except ImportError:  # pragma: no cover - celery isteğe bağlıdır
    app = None
