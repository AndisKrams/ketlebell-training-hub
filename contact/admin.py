from django.contrib import admin
from .models import ContactMessage, ContactSettings


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'order', 'subject', 'created', 'copied_to_email')
    list_filter = ('copied_to_email', 'created')
    search_fields = ('user__username', 'user__email', 'order__order_number', 'subject', 'message')


@admin.register(ContactSettings)
class ContactSettingsAdmin(admin.ModelAdmin):
    list_display = ('days_after_order', 'forward_to_email')
from django.contrib import admin
