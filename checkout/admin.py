from django.contrib import admin

from .models import Order, OrderLineItem


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'full_name', 'date', 'total', 'status', 'paid')
    search_fields = ('order_number', 'full_name', 'email')
    list_filter = ('status', 'date', 'paid')
    actions = ['mark_as_dispatched']

    def mark_as_dispatched(self, request, queryset):
        updated = queryset.update(status=Order.STATUS_DISPATCHED)
        self.message_user(request, f"Marked {updated} order(s) as dispatched")
    mark_as_dispatched.short_description = 'Mark selected orders as dispatched'


@admin.register(OrderLineItem)
class OrderLineItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'quantity', 'price')
    search_fields = ('product_name',)
