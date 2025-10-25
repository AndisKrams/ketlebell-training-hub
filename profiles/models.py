from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """Profile model used to store default delivery information and
    contact details.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    default_phone_number = models.CharField(
        max_length=20, blank=True, null=True
    )
    default_postcode = models.CharField(max_length=20, blank=True, null=True)
    default_town_or_city = models.CharField(
        max_length=40, blank=True, null=True
    )
    default_street_address1 = models.CharField(
        max_length=80, blank=True, null=True
    )
    default_street_address2 = models.CharField(
        max_length=80, blank=True, null=True
    )
    default_county = models.CharField(max_length=80, blank=True, null=True)
    default_country = models.CharField(max_length=40, blank=True, null=True)
    # Stripe customer id for saving payment methods
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Profile for {self.user.username}"


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Create or update user profile when the User object is saved."""
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Ensure profile exists; create if it's missing
        try:
            instance.userprofile.save()
        except UserProfile.DoesNotExist:
            UserProfile.objects.create(user=instance)
