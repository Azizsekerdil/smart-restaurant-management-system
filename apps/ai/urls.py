from django.urls import path

from apps.ai import views

app_name = "ai"

urlpatterns = [
    path("", views.assistant, name="assistant"),
    path("sor/", views.assistant_ask, name="assistant_ask"),
    path("akis/", views.assistant_stream, name="assistant_stream"),
    path("analizler/", views.analysis_hub, name="analysis_hub"),
    path("analiz/<str:kind>/", views.run_analysis, name="run_analysis"),
    path("icgoruler/", views.insights, name="insights"),
    path(
        "urun/<int:product_id>/aciklama/", views.generate_description, name="generate_description"
    ),
    path(
        "urun/<int:product_id>/fiyat-simulasyon/", views.price_simulation, name="price_simulation"
    ),
    path("saglayicilar/", views.provider_settings, name="providers"),
    path("saglayicilar/<str:key>/test/", views.test_provider, name="test_provider"),
    path("saglayicilar/test-hepsi/", views.test_all, name="test_all"),
    path("saglayicilar/devre-sifirla/", views.reset_breakers, name="reset_breakers"),
    path("kullanim/", views.usage_log, name="usage_log"),
]
