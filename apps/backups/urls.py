from django.urls import path

from apps.backups import views

app_name = "backups"

urlpatterns = [
    path("", views.index, name="index"),
    path("olustur/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/indir/", views.download, name="download"),
    path("<int:pk>/geri-yukle/", views.restore, name="restore"),
    path("<int:pk>/sil/", views.delete, name="delete"),
]
