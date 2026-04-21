from django.core.management.base import BaseCommand
from yukta.tasks import run_strategy

class Command(BaseCommand):
    help = "Run strategy via Dramatiq"

    def handle(self, *args, **kwargs):
        run_strategy.send()
        self.stdout.write("Strategy task sent")