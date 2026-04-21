from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MarketDataViewSet, index, run_backtest_view

router = DefaultRouter()
router.register(r'marketdata', MarketDataViewSet)

urlpatterns = [
    # 👉 Dashboard UI
    path('', index, name='home'),

    # 👉 Backtest
    path('run/', run_backtest_view, name='run_backtest'),

    # 👉 API (separate)
    path('api/', include(router.urls)),
]