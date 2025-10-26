from django.db import models
from django.conf import settings


class ContactSettings(models.Model):
    """Admin-editable settings controlling contact availability.

    Keep it simple: site admins can edit this model in the admin. The
    app will use the first object when present, otherwise defaults are
    used (42 days, no forward email).
    """
    days_after_order = models.PositiveIntegerField(default=42)
    forward_to_email = models.EmailField(blank=True, null=True)

    class Meta:
        verbose_name = 'Contact settings'
        verbose_name_plural = 'Contact settings'

    def __str__(self):
        return f"Contact settings (days_after_order={self.days_after_order})"


class ContactMessage(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contact_messages',
    )
    order = models.ForeignKey(
        'checkout.Order', on_delete=models.CASCADE, related_name='contact_messages'
    )
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    copied_to_email = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created']

    def __str__(self):
        who = self.user.get_full_name() if self.user else 'Anonymous'
        return f"Message from {who} about {self.order.order_number}"
from django.db import models
