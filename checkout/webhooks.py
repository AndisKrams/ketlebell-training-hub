import json
import logging

from django.http import HttpResponse
from django.conf import settings

from .models import Order
from basket.models import Basket


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

    # Handle event types we care about (checkout.session.completed and
    # payment_intent.succeeded). When we mark an order as paid we also
    # clear the authenticated user's DB basket when possible.
    kind = event.get('type')
    if kind in ('checkout.session.completed', 'payment_intent.succeeded'):
        obj = event.get('data', {}).get('object', {})
        metadata = obj.get('metadata', {}) or {}
        order_number = metadata.get('order_number')
        if order_number:
            try:
                order = Order.objects.get(order_number=order_number)
                # Mark order as paid and update status so the user sees
                # it as awaiting delivery in their profile.
                order.paid = True
                order.status = Order.STATUS_PAID
                order.save()

                # Clear DB basket for authenticated owner if present
                try:
                    if order.profile and order.profile.user:
                        try:
                            basket_obj = Basket.objects.get(
                                user=order.profile.user
                            )
                            basket_obj.items.all().delete()
                        except Basket.DoesNotExist:
                            pass
                except Exception:
                    # ignore any issues when accessing profile/user
                    pass
            except Order.DoesNotExist:
                logger.warning('Webhook: order not found: %s', order_number)

    # Return 200 for all handled/ignored events
    return HttpResponse(status=200)
