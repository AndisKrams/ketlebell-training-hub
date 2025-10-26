from django.contrib import admin
from .models import ContactMessage, ContactSettings


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    def message_snippet(self, obj):
        if not obj.message:
            return ''
        text = obj.message
        return (text[:75] + '...') if len(text) > 75 else text

    message_snippet.short_description = 'Message'

    list_display = ('id', 'user', 'order', 'subject', 'message_snippet', 'created', 'copied_to_email')
    list_filter = ('copied_to_email', 'created')
    search_fields = ('user__username', 'user__email', 'order__order_number', 'subject', 'message')
    readonly_fields = ('message', 'created',)


@admin.register(ContactSettings)
class ContactSettingsAdmin(admin.ModelAdmin):
    list_display = ('days_after_order', 'forward_to_email')
