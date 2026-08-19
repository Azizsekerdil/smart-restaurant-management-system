"""Kök pytest yapılandırması.

Django ayarları içe aktarılmadan ÖNCE test ortamı değişkenlerini belirler.
Bu dosya pytest tarafından her şeyden önce yüklenir.
"""

import os

os.environ.setdefault("DJANGO_ENV", "test")
os.environ.setdefault("DJANGO_DEBUG", "False")
os.environ.setdefault("DB_ENGINE", "sqlite")
# Testler dış ağa çıkmasın: bulut sağlayıcılar kapalı, yerel sunucu erişilemez adres.
os.environ.setdefault("LMSTUDIO_ENABLED", "False")
os.environ.setdefault("NVIDIA_ENABLED", "False")
os.environ.setdefault("OPENAI_ENABLED", "False")
os.environ.setdefault("ANTHROPIC_ENABLED", "False")
os.environ.setdefault("GEMINI_ENABLED", "False")
os.environ.setdefault("OPENROUTER_ENABLED", "False")
os.environ.setdefault("OLLAMA_ENABLED", "False")
os.environ.setdefault("DEVCENTER_ENABLED", "True")
os.environ.setdefault("DEVCENTER_TERMINAL_ENABLED", "True")
