

from django.urls import path

from .views import Stocks

urlpatterns = [
    path('', Stocks.as_view(), name='stocks'),
    path('<int:pk>/', Stocks.as_view(), name='stock-detail'),
]
