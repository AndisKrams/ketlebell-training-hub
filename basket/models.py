from django.conf import settings
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


class Basket(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="baskets",
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Basket for {self.user} (updated {self.updated:%Y-%m-%d %H:%M})"


class BasketItem(models.Model):
    basket = models.ForeignKey(
        Basket,
        on_delete=models.CASCADE,
        related_name="items",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    quantity = models.PositiveIntegerField(default=1)
    price_snapshot = models.DecimalField(max_digits=9, decimal_places=2)

    class Meta:
        unique_together = ("basket", "content_type", "object_id")

    def __str__(self):
        return f"{self.quantity} x {self.content_object} in {self.basket}"
