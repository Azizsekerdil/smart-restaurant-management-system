from django.contrib import admin

from apps.backups.models import BackupRecord, RestoreRecord


@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = ("filename", "kind", "status", "size_mb", "started_at", "created_by")
    list_filter = ("kind", "status", "includes_secrets")
    search_fields = ("filename", "note")
    readonly_fields = (
        "filename",
        "kind",
        "status",
        "size_bytes",
        "checksum",
        "started_at",
        "finished_at",
        "contents",
        "includes_secrets",
        "error_message",
    )

    def has_add_permission(self, request):
        # Yedek yalnızca yedekleme servisi üzerinden oluşturulur; elle
        # eklenen bir kayıt diskteki dosyayla eşleşmez.
        return False


@admin.register(RestoreRecord)
class RestoreRecordAdmin(admin.ModelAdmin):
    list_display = ("source_filename", "status", "created_at", "created_by")
    list_filter = ("status",)
    readonly_fields = ("source_filename", "safety_backup", "status", "error_message")

    def has_add_permission(self, request):
        return False
