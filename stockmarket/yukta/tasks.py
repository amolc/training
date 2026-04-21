
import dramatiq
from dramatiq.brokers.redis import RedisBroker

dramatiq.set_broker(RedisBroker(url="redis://127.0.0.1:6379/0"))

from yukta.models import BacktestResult
@dramatiq.actor
def run_strategy():
    from yukta.services.backtest import run_backtest
    print("🚀 Task Started...")

    result = run_backtest()

    BacktestResult.objects.create(
        chart=result["chart"],
        roi_chart=result["roi_chart"],
        total_pnl=result["total_pnl"],
        win_rate=result["win_rate"],
    )
    print("🔥 Backtest executed")