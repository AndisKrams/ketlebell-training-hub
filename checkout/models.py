from decimal import Decimal
import uuid

from django.db import models


class Order(models.Model):
    """A simple order model to store checkout information."""

    order_number = models.CharField(max_length=32, unique=True, editable=False)
    profile = models.ForeignKey(
        'profiles.UserProfile', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='orders'
    )
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True)
    street_address1 = models.CharField(max_length=80)
    street_address2 = models.CharField(max_length=80, blank=True)
    town_or_city = models.CharField(max_length=40)
    postcode = models.CharField(max_length=20)
    county = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=40)

    date = models.DateTimeField(auto_now_add=True)
    original_basket = models.TextField(blank=True, null=True)
    total = models.DecimalField(
        max_digits=9, decimal_places=2, default=Decimal('0.00')
    )

    def _generate_order_number(self):
        return uuid.uuid4().hex.upper()

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_number} - £{self.total}"


class OrderLineItem(models.Model):
    order = models.ForeignKey(
        Order, related_name='items', on_delete=models.CASCADE
    )
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=7, decimal_places=2)

    def __str__(self):
        order_num = self.order.order_number
        return f"{self.quantity} x {self.product_name} in {order_num}"
