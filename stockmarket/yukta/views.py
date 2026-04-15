from rest_framework.viewsets import ModelViewSet
from .models import MarketData
from .serializers import MarketDataSerializer


class MarketDataViewSet(ModelViewSet):
    queryset = MarketData.objects.all()
    serializer_class = MarketDataSerializer