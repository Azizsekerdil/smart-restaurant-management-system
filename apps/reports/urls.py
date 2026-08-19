from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("raporlar/", views.report_index, name="report_index"),
    path("istatistik/", views.statistics_center, name="statistics"),
    path("raporlar/satis/", views.sales_report, name="sales_report"),
    path("raporlar/karlilik/", views.profitability_report, name="profitability"),
    path("raporlar/iptaller/", views.void_report, name="void_report"),
    path("raporlar/gunsonu/", views.daily_closing_list, name="daily_closing_list"),
    path("raporlar/gunsonu/olustur/", views.daily_closing_generate, name="daily_closing_generate"),
    path("raporlar/gunsonu/<int:pk>/", views.daily_closing_detail, name="daily_closing_detail"),
    path("raporlar/gunsonu/<int:pk>/pdf/", views.daily_closing_pdf, name="daily_closing_pdf"),
    path("raporlar/giderler/", views.expense_list, name="expense_list"),
    path("raporlar/giderler/ekle/", views.expense_create, name="expense_create"),
    # Dışa aktarma
    path("disa-aktar/satis.xlsx", views.export_sales_excel, name="export_sales_excel"),
    path("disa-aktar/satis.csv", views.export_sales_csv, name="export_sales_csv"),
    path("disa-aktar/satis.pdf", views.export_sales_pdf, name="export_sales_pdf"),
    path("disa-aktar/stok.xlsx", views.export_inventory_excel, name="export_inventory_excel"),
    path("disa-aktar/istatistik.xlsx", views.export_statistics_excel, name="export_statistics"),
]
