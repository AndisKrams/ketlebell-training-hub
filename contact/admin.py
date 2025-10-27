from django.contrib import admin
from .models import ContactMessage, ContactSettings
from django.utils.html import escape
from django.utils.safestring import mark_safe


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    def message_snippet(self, obj):
        if not obj.message:
            return ''
        text = obj.message
        return (text[:75] + '...') if len(text) > 75 else text

    message_snippet.short_description = 'Message'

    def message_box(self, obj):
        """Render the message inside a readonly textarea so it wraps nicely
        and is fully visible in the admin detail view."""
        if not obj or not obj.message:
            return ''
        # Escape to prevent XSS, but render inside a textarea for readability
        return mark_safe(
            f"<textarea readonly rows=8 cols=80 style=\"width:100%\">{escape(obj.message)}</textarea>"
        )

    message_box.short_description = 'Message'

    list_display = (
        'id', 'user', 'order', 'subject', 'message_snippet', 'created', 'copied_to_email'
    )
    list_filter = ('copied_to_email', 'created')
    search_fields = ('user__username', 'user__email', 'order__order_number', 'subject', 'message')
    readonly_fields = ('message_box', 'created',)


@admin.register(ContactSettings)
class ContactSettingsAdmin(admin.ModelAdmin):
    list_display = ('days_after_order', 'forward_to_email')

    def has_add_permission(self, request):
        # Allow creating the settings object only if none exists
        if ContactSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion from the admin to keep a stable single settings instance
        return False

    def changelist_view(self, request, extra_context=None):
        """Redirect the changelist to the single settings object's change page
        when it exists. This makes the admin surface behave like a singleton
        editor: admins click the app and are taken straight to the settings.
        """
        obj = ContactSettings.objects.first()
        if obj:
            from django.shortcuts import redirect

            return redirect(f"../{obj.id}/change/")
        return super().changelist_view(request, extra_context=extra_context)
