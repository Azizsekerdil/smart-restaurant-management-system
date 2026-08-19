from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.RestaurantLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dil/", views.switch_language, name="switch_language"),
    path("profil/", views.profile, name="profile"),
    path("parola/", views.password_change, name="password_change"),
    path("pin/", views.set_pin, name="set_pin"),
    path("pin/gecis/", views.pin_switch, name="pin_switch"),
    path("kullanicilar/", views.user_list, name="user_list"),
    path("kullanicilar/yeni/", views.user_create, name="user_create"),
    path("kullanicilar/<int:pk>/duzenle/", views.user_edit, name="user_edit"),
    path("kullanicilar/<int:pk>/izinler/", views.user_permissions, name="user_permissions"),
    path("kullanicilar/<int:pk>/durum/", views.user_toggle_active, name="user_toggle_active"),
]
