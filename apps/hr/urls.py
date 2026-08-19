from django.urls import path

from apps.hr import views

app_name = "hr"

urlpatterns = [
    path("", views.employee_list, name="employee_list"),
    path("yeni/", views.employee_create, name="employee_create"),
    path("<int:pk>/", views.employee_detail, name="employee_detail"),
    path("<int:pk>/puantaj/", views.attendance_toggle, name="attendance_toggle"),
    path("vardiya/", views.shift_schedule, name="shift_schedule"),
    path("vardiya/ata/", views.shift_assign, name="shift_assign"),
    path("vardiya/<int:pk>/sil/", views.shift_remove, name="shift_remove"),
    path("izin/", views.leave_list, name="leave_list"),
    path("izin/ekle/", views.leave_create, name="leave_create"),
    path("izin/<int:pk>/karar/", views.leave_decide, name="leave_decide"),
    path("gorevler/", views.task_list, name="task_list"),
    path("gorevler/ekle/", views.task_create, name="task_create"),
    path("gorevler/<int:pk>/tamamla/", views.task_complete, name="task_complete"),
    path("performans/", views.performance_report, name="performance"),
]
