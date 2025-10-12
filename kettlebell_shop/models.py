from django.db import models


class Kettlebell(models.Model):
    WEIGHT_CHOICES = [
        (8, '8 kg'), (12, '12 kg'), (16, '16 kg'), (20, '20 kg'),
        (24, '24 kg'), (28, '28 kg'), (32, '32 kg'), (36, '36 kg'),
        (40, '40 kg'), (48, '48 kg')
        ]
    weight = models.PositiveIntegerField(choices=WEIGHT_CHOICES, unique=True)
    stock = models.PositiveIntegerField(default=0)
    price_gbp = models.DecimalField(max_digits=7, decimal_places=2, default=0.00, help_text="Price in GBP")

    def __str__(self):
        return f"{self.weight} kg (£{self.price_gbp}, {self.stock} in stock)"
