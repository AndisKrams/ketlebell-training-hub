from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .forms import UserProfileForm
from .models import UserProfile
try:
    # contact app is optional; import at runtime to avoid startup errors
    from contact.models import ContactSettings
except Exception:
    ContactSettings = None
from django.conf import settings


def _get_saved_payment_methods(profile):
    """Return a list of saved card payment methods for the given profile.

    Each entry is a dict with brand, last4, exp_month, exp_year and id.
    If Stripe is not configured or no customer is present, returns empty list.
    """
    pm_list = []
    if not profile or not getattr(profile, 'stripe_customer_id', None):
        return pm_list

    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        methods = stripe.PaymentMethod.list(
            customer=profile.stripe_customer_id, type='card'
        )
        # Try to determine the customer's default payment method (if set)
        default_pm = None
        try:
            cust = stripe.Customer.retrieve(profile.stripe_customer_id)
            default_pm = (
                (cust.get('invoice_settings') or {}).get('default_payment_method')
                or cust.get('default_source')
            )
        except Exception:
            default_pm = None
        for m in methods.get('data', []):
            card = m.get('card', {})
            pm_list.append(
                {
                    'id': m.get('id'),
                    'brand': card.get('brand'),
                    'last4': card.get('last4'),
                    'exp_month': card.get('exp_month'),
                    'exp_year': card.get('exp_year'),
                    'is_default': True if default_pm and m.get('id') == default_pm else False,
                }
            )
    except Exception:
        # If Stripe is misconfigured or call fails, return empty list
        return []

    return pm_list


@login_required
def profile_view(request):
    """Render and update the user's profile. Orders are optional."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully')
            return redirect('profiles:profile')
        messages.error(request, 'Please correct the errors below')
    else:
        form = UserProfileForm(instance=profile)

    # Load the user's orders (if any) ordered by date desc
    orders = profile.orders.all().order_by('-date')

    # Fetch saved payment methods (masked) from Stripe when available
    payment_methods = _get_saved_payment_methods(profile)

    # Determine contact availability window (days) from ContactSettings
    days_allowed = 42
    if ContactSettings is not None:
        try:
            cfg = ContactSettings.objects.first()
            if cfg and getattr(cfg, 'days_after_order', None) is not None:
                days_allowed = cfg.days_after_order
        except Exception:
            pass

    # Annotate each order with whether contact is allowed (used by template)
    from django.utils import timezone
    for o in orders:
        allowed = False
        try:
            # Allow contact for paid and dispatched orders within the window
            if o.status in ('paid', 'dispatched'):
                cutoff = o.date + timezone.timedelta(days=days_allowed)
                if timezone.now() <= cutoff:
                    allowed = True
        except Exception:
            allowed = False
        # attach attribute for template use
        setattr(o, 'contact_allowed', allowed)

    return render(
        request,
        'profiles/profile.html',
        {
            'form': form,
            'orders': orders,
            'payment_methods': payment_methods,
            'contact_days_allowed': days_allowed,
        },
    )


@login_required
def remove_payment_method(request, pm_id):
    """Detach a saved payment method from the customer's Stripe account.

    Only allows the authenticated user's saved payment methods to be removed.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method != 'POST':
        messages.error(request, 'Invalid request method')
        return redirect('profiles:profile')

    if not profile.stripe_customer_id:
        messages.error(
            request, 'No Stripe customer configured for your account'
        )
        return redirect('profiles:profile')

    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        pm = stripe.PaymentMethod.retrieve(pm_id)
        # Ensure the payment method belongs to the logged-in user's customer
        pm_customer = pm.get('customer')
        if not pm_customer or pm_customer != profile.stripe_customer_id:
            messages.error(
                request, 'Payment method not found for your account'
            )
            return redirect('profiles:profile')

        # Detach the payment method
        stripe.PaymentMethod.detach(pm_id)
        messages.success(request, 'Payment method removed')
    except Exception as e:
        messages.error(request, f'Could not remove payment method: {e}')

    return redirect('profiles:profile')
