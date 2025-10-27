from django.contrib import admin

from .models import Order, OrderLineItem
from contact.models import ContactMessage


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'full_name', 'date', 'total', 'status', 'paid'
    )
    search_fields = ('order_number', 'full_name', 'email')
    list_filter = ('status', 'date', 'paid')
    actions = ['mark_as_dispatched']

    # Show contact messages in the Order admin detail view so staff can
    # read full customer messages alongside the order.
    class ContactMessageInline(admin.StackedInline):
        model = ContactMessage
        fields = (
            'user', 'subject', 'message_box', 'created', 'copied_to_email'
        )
        readonly_fields = (
            'user',
            'subject',
            'message_box',
            'created',
            'copied_to_email',
        )
        extra = 0
        can_delete = False

        def message_box(self, obj):
            from django.utils.html import escape
            from django.utils.safestring import mark_safe

            if not obj or not obj.message:
                return ''
            textarea = (
                '<textarea readonly rows="6" cols="60" '
                'style="width:100%">' + escape(obj.message) + '</textarea>'
            )
            return mark_safe(textarea)

        message_box.short_description = 'Message'

    inlines = [ContactMessageInline]

    def mark_as_dispatched(self, request, queryset):
        updated = queryset.update(status=Order.STATUS_DISPATCHED)
        self.message_user(request, f"Marked {updated} order(s) as dispatched")
    mark_as_dispatched.short_description = 'Mark selected orders as dispatched'


@admin.register(OrderLineItem)
class OrderLineItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'quantity', 'price')
    search_fields = ('product_name',)
