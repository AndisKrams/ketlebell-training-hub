import json
import logging

from django.http import HttpResponse
from django.conf import settings

from .models import Order


logger = logging.getLogger(__name__)


def webhook(request):
    """Handle Stripe webhook events.

    Verifies signature when STRIPE_WH_SECRET is configured. On
    checkout.session.completed events, attempts to mark the matching
    Order as paid if a `paid` field exists on the model.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        if settings.STRIPE_WH_SECRET:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WH_SECRET
            )
        else:
            event = json.loads(payload)
    except Exception as e:
        logger.exception('Failed to parse/verify Stripe webhook: %s', e)
        return HttpResponse(status=400)

    # Handle event types we care about
    kind = event.get('type')
    if kind == 'checkout.session.completed':
        session = event.get('data', {}).get('object', {})
        metadata = session.get('metadata', {}) or {}
        order_number = metadata.get('order_number')
        if order_number:
            try:
                order = Order.objects.get(order_number=order_number)
                # If model has a 'paid' boolean, set it. Otherwise do not
                # attempt schema changes here.
                if hasattr(order, 'paid'):
                    order.paid = True
                    order.save()
            except Order.DoesNotExist:
                logger.warning('Webhook: order not found: %s', order_number)

    # Return 200 for all handled/ignored events
    return HttpResponse(status=200)
