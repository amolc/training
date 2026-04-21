from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MarketDataViewSet, index, run_backtest_view
router = DefaultRouter()
router.register(r'marketdata', MarketDataViewSet)
urlpatterns = [
    path('', index, name='home'),
    path('run/', run_backtest_view, name='run_backtest'),
    path('api/', include(router.urls)),
]