from django.contrib import admin
from .models import Basket, BasketItem


@admin.register(Basket)
class BasketAdmin(admin.ModelAdmin):
    list_display = ("user", "updated", "created")
    readonly_fields = ("created", "updated")


@admin.register(BasketItem)
class BasketItemAdmin(admin.ModelAdmin):
    list_display = ("basket", "content_object", "quantity", "price_snapshot")
