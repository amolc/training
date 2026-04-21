import os
import django
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stockmarket.settings")
django.setup()

from yukta.tasks import run_strategy

logging.basicConfig(level=logging.INFO)

scheduler = BlockingScheduler()

def job():
    print("⏱ Sending task to Dramatiq...")
    run_strategy.send()

scheduler.add_job(
    job,
    trigger='interval',
    minutes=5,   # ✅ every 5 minutes
    id='run_strategy_job',
    replace_existing=True,
    max_instances=1
)

print("Scheduler started...")

scheduler.start()