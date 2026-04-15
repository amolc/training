from django.db import models

# Create your models here.
#stock - buy- sell- google sheet model
class MarketData(models.Model):
    stock = models.CharField(max_length=50)
    date = models.DateTimeField()
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    ha_open = models.FloatField()
    ha_high = models.FloatField()
    ha_low = models.FloatField()
    ha_close = models.FloatField()
    ema_high = models.FloatField()
    ema_low = models.FloatField()
    signal = models.CharField(max_length=50, null=True)
    entry_time = models.DateTimeField(null=True, blank=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    exit_type = models.CharField(max_length=20, null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.stock} {self.date}"