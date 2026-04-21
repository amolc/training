from django.shortcuts import render
from django.core.cache import cache
from rest_framework.viewsets import ModelViewSet
from .models import MarketData
from yukta.models import BacktestResult
from .serializers import MarketDataSerializer, BacktestResultSerializer
from .services.backtest import run_backtest

def index(request):
    latest = BacktestResult.objects.order_by('-created_at').first()
    cached_result = cache.get("yukta_last_result", {})
    if not cached_result:
        print("No cache found. Running backtest...")
        cached_result = run_backtest({})
        cache.set("yukta_last_result", cached_result)
        return render(request, "result.html", {
            "result": cached_result,
            "latest": latest
        })
    session_trades = request.session.get("yukta_trades", [])
    session_total_trades = request.session.get("yukta_total_trades", 0)
    session_roi_overall = request.session.get("yukta_roi_overall", 0)
    trades = session_trades or cached_result.get("trades", [])
    total_trades = session_total_trades or cached_result.get("total_trades", 0) or len(trades)
    roi_overall = session_roi_overall or cached_result.get("roi_overall", 0)
    buy_trades = [t for t in trades if t.get("type") == "BUY"]
    sell_trades = [t for t in trades if t.get("type") == "SELL"]
    result = {
        "chart": latest.chart if latest else cached_result.get("chart"),
        "roi_chart": latest.roi_chart if latest else cached_result.get("roi_chart"),
        "total_pnl": latest.total_pnl if latest else cached_result.get("total_pnl", 0),
        "win_rate": latest.win_rate if latest else cached_result.get("win_rate", 0),
        "trades": trades,
        "total_trades": total_trades,
        "roi_overall": roi_overall,
        "profitloss_chart": cached_result.get("profitloss_chart"),
        "total_signals": cached_result.get("total_signals", len(trades)),
        "buy_signals": cached_result.get("buy_signals", len(buy_trades)),
        "sell_signals": cached_result.get("sell_signals", len(sell_trades)),
        "buy_strategy": cached_result.get("buy_strategy"),
        "sell_strategy": cached_result.get("sell_strategy"),
    }
    return render(request, "result.html", {
        "result": result,
        "latest": latest
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
    try:
        result = run_backtest(params)
    except Exception as e:
        return render(request, "error.html", {"error": str(e)})
    request.session["yukta_trades"] = result.get("trades", [])
    request.session["yukta_total_trades"] = result.get("total_trades", 0)
    request.session["yukta_roi_overall"] = result.get("roi_overall", 0)
    cache.set("yukta_last_result", result, timeout=None)
    saved = BacktestResult.objects.create(
        chart=result["chart"],
        roi_chart=result.get("roi_chart"),
        total_pnl=result["total_pnl"],
        win_rate=result["win_rate"],
    )
    latest = saved
    return render(request, "result.html", {
        "result": result,
        "latest": latest
    })

class MarketDataViewSet(ModelViewSet):
    queryset = MarketData.objects.all()
    serializer_class = MarketDataSerializer
