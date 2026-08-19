from django.urls import path

from apps.devcenter import views

app_name = "devcenter"

urlpatterns = [
    path("", views.index, name="index"),
    path("dosyalar/", views.file_browser, name="files"),
    path("terminal/", views.terminal, name="terminal"),
    path("terminal/kontrol/", views.terminal_check, name="terminal_check"),
    path("terminal/calistir/", views.terminal_run, name="terminal_run"),
    path("oneri/olustur/", views.proposal_create, name="proposal_create"),
    path("oneri/<int:pk>/", views.proposal_detail, name="proposal_detail"),
    path("oneri/<int:pk>/test/", views.proposal_test, name="proposal_test"),
    path("oneri/<int:pk>/uygula/", views.proposal_apply, name="proposal_apply"),
    path("oneri/<int:pk>/geri-al/", views.proposal_revert, name="proposal_revert"),
    path("oneri/<int:pk>/reddet/", views.proposal_reject, name="proposal_reject"),
    path("git/", views.git_panel, name="git"),
    path("git/commit-onerisi/", views.git_commit_suggestion, name="git_commit_suggestion"),
    path("geri-alma/", views.snapshot_list, name="snapshots"),
    path("geri-alma/<int:pk>/yukle/", views.snapshot_restore, name="snapshot_restore"),
]
