from django.db import models

# Create your models here.


class Stock(models.Model):
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    price = models.FloatField()
    volume = models.FloatField()

    def __str__(self):
        return str(self.name)
