from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from .models import MarketData
from yukta.models import BacktestResult
from .serializers import MarketDataSerializer, BacktestResultSerializer
from .services.backtest import run_backtest


def index(request):
    latest = BacktestResult.objects.order_by('-created_at').first()

    result = {
        "chart": latest.chart if latest else None,
        "roi_chart": latest.roi_chart if latest else None,
        "total_pnl": latest.total_pnl if latest else 0,
        "win_rate": latest.win_rate if latest else 0,
    }

    return render(request, "index.html", {
        "result": result,
        "latest": latest   # ✅ REQUIRED
    })



def run_backtest_view(request):

    params = {
        "investment": request.GET.get("investment"),
        "ema_8": request.GET.get("ema_8"),
        "ema_14": request.GET.get("ema_14"),
        "ema_50": request.GET.get("ema_50"),
        "lips_period": request.GET.get("lips_period"),
        "lips_shift": request.GET.get("lips_shift"),
    }

    result = run_backtest(params)
    
    #save result to db
    saved=BacktestResult.objects.create(
        chart=result["chart"],
        roi_chart=result.get("roi_chart"),
        total_pnl=result["total_pnl"],
        win_rate=result["win_rate"],
        )
    
    latest=BacktestResult.objects.order_by('-created_at').first()

    return render(request, "result.html", {"result": result, "latest": latest})

class MarketDataViewSet(ModelViewSet):
    queryset = MarketData.objects.all()
    serializer_class = MarketDataSerializer