from django.urls import path

from apps.training import views

app_name = "training"

urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:key>/", views.lesson, name="lesson"),
    path("<slug:key>/tamamla/", views.complete, name="complete"),
    path("<slug:key>/sifirla/", views.reset, name="reset"),
]
