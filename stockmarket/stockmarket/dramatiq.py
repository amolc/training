import os
import django

from dramatiq import set_broker
from dramatiq.brokers.redis import RedisBroker

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stockmarket.settings")
django.setup()

broker = RedisBroker(url="redis://127.0.0.1:6379/0")
set_broker(broker)