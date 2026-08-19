"""REST API kök yönlendiricisi."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.catalog.api import CategoryViewSet, ProductViewSet
from apps.crm.api import CustomerViewSet
from apps.floor.api import ReservationViewSet, TableViewSet
from apps.inventory.api import IngredientViewSet, StockMovementViewSet
from apps.kitchen.api import KitchenTicketViewSet
from apps.orders.api import OrderViewSet

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("tables", TableViewSet, basename="table")
router.register("reservations", ReservationViewSet, basename="reservation")
router.register("orders", OrderViewSet, basename="order")
router.register("tickets", KitchenTicketViewSet, basename="ticket")
router.register("ingredients", IngredientViewSet, basename="ingredient")
router.register("stock-movements", StockMovementViewSet, basename="stockmovement")
router.register("customers", CustomerViewSet, basename="customer")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("ai/", include("apps.ai.api_urls")),
]
