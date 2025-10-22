from django.contrib import admin

from .models import Order, OrderLineItem


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'full_name', 'date', 'total')
    search_fields = ('order_number', 'full_name', 'email')


@admin.register(OrderLineItem)
class OrderLineItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'quantity', 'price')
    search_fields = ('product_name',)
