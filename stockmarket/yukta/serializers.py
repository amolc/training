from rest_framework import serializers
from .models import MarketData, BacktestResult

class MarketDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketData
        fields = '__all__'

class BacktestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestResult
        fields = '__all__'