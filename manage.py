#!/usr/bin/env python
"""Django yönetim komut satırı aracı - Akıllı Restaurant Yönetim Sistemi."""

import os
import sys
from pathlib import Path


def main() -> None:
    # Proje kökünü import yoluna ekle (apps.* paketleri için).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django içe aktarılamadı. Sanal ortamın etkin olduğundan emin olun:\n"
            "    .\\.venv\\Scripts\\Activate.ps1\n"
            "    pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
