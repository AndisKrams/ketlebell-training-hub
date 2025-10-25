import json
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest

from .forms import OrderForm
from .models import Order, OrderLineItem
from basket.models import Basket
from kettlebell_shop.models import Kettlebell


def create_checkout_session(request, order_number):
    """Create a Stripe Checkout Session for an existing Order and
    redirect the user to the hosted Stripe checkout page.

    This view expects the order to already exist (created by the
    standard checkout view). It will build line items from the
    OrderLineItem rows.
    """
    try:
        import stripe
    except Exception:
        messages.error(request, 'Stripe library not installed')
        return redirect('checkout:checkout')

    stripe.api_key = settings.STRIPE_SECRET_KEY

    order = get_object_or_404(Order, order_number=order_number)

    # Build Stripe line items from order items
    stripe_items = []
    for it in order.items.all():
        # Stripe expects unit_amount in the smallest currency unit (pence)
        unit_amount = int((it.price * Decimal('100')).to_integral_value())
        stripe_items.append(
            {
                'price_data': {
                    'currency': settings.STRIPE_CURRENCY,
                    'product_data': {'name': it.product_name},
                    'unit_amount': unit_amount,
                },
                'quantity': it.quantity,
            }
        )

    success_url = request.build_absolute_uri(
        reverse(
            'checkout:checkout_success',
            kwargs={'order_number': order.order_number},
        )
    )
    cancel_url = request.build_absolute_uri(reverse('checkout:checkout'))

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=stripe_items,
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={'order_number': order.order_number},
        )
    except Exception as e:
        messages.error(request, f'Could not create Stripe session: {e}')
        return redirect('checkout:checkout')

    # Redirect to the Stripe hosted checkout page
    return redirect(session.url)


@require_POST
def create_payment_intent(request, order_number):
    """Create a Stripe PaymentIntent for an existing order.

    Expects JSON body: {"save_card": true|false}
    Returns: JSON with client_secret and stripe_public_key.
    """
    try:
        import stripe
    except Exception:
        return JsonResponse({'error': 'Stripe library not installed'}, status=500)

    order = get_object_or_404(Order, order_number=order_number)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        body = {}

    save_card = bool(body.get('save_card'))

    stripe.api_key = settings.STRIPE_SECRET_KEY

    # compute amount in pence
    try:
        amount = int((order.total * Decimal('100')).to_integral_value())
    except Exception:
        return JsonResponse({'error': 'Invalid order total'}, status=400)

    customer_id = None
    if request.user.is_authenticated:
        try:
            profile = request.user.userprofile
            customer_id = profile.stripe_customer_id
        except Exception:
            profile = None
    else:
        profile = None

    # If user wants to save card, ensure we have a Stripe Customer
    if save_card:
        if not customer_id and request.user.is_authenticated:
            # create a customer
            try:
                cust = stripe.Customer.create(
                    email=order.email,
                    name=order.full_name,
                )
                customer_id = cust['id']
                if profile is not None:
                    profile.stripe_customer_id = customer_id
                    profile.save()
            except Exception as e:
                return JsonResponse({'error': f'Could not create customer: {e}'}, status=500)

    try:
        pi_kwargs = {
            'amount': amount,
            'currency': settings.STRIPE_CURRENCY,
            'metadata': {'order_number': order.order_number},
        }
        if customer_id:
            pi_kwargs['customer'] = customer_id
        if save_card:
            # signal Stripe to save payment method for future off-session use
            pi_kwargs['setup_future_usage'] = 'off_session'

        intent = stripe.PaymentIntent.create(**pi_kwargs)
    except Exception as e:
        return JsonResponse({'error': f'Could not create payment intent: {e}'}, status=500)

    return JsonResponse({
        'client_secret': intent.client_secret,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    })


def checkout(request):
    """Simple checkout view: shows form and creates an Order.

    This implementation expects a server-side basket retrieval.
    """

    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            # attach profile when available
            if request.user.is_authenticated:
                try:
                    order.profile = request.user.userprofile
                except Exception:
                    # ignore if profile is missing
                    pass

            # snapshot the session basket for debugging/audit
            order.original_basket = json.dumps(
                request.session.get('basket', {})
            )

            # create order and line items atomically
            with transaction.atomic():
                order.save()  # generate order_number via model save

                total = Decimal('0.00')

                # Authenticated users: copy from BasketItem objects
                if request.user.is_authenticated:
                    basket_obj, _ = Basket.objects.get_or_create(
                        user=request.user
                    )
                    for it in basket_obj.items.select_related('content_type'):
                        qty = int(it.quantity)
                        price = Decimal(it.price_snapshot)
                        name = str(it.content_object)
                        OrderLineItem.objects.create(
                            order=order,
                            product_name=name,
                            quantity=qty,
                            price=price,
                        )
                        total += price * qty
                    # clear DB basket items now we've copied them
                    basket_obj.items.all().delete()
                else:
                    # Session-based anonymous basket format:
                    # {weight_str: {quantity, price_gbp}}
                    session_basket = request.session.get('basket', {})
                    for weight_str, data in (session_basket or {}).items():
                        qty = int(data.get('quantity', 0))
                        try:
                            price = Decimal(str(data.get('price_gbp', '0')))
                        except InvalidOperation:
                            price = Decimal('0.00')

                        # try to map to a product for a nicer name
                        name = f"{weight_str} kg kettlebell"
                        try:
                            w = Decimal(str(weight_str))
                            kb = Kettlebell.objects.filter(
                                weight=w, weight_unit='kg'
                            ).first()
                            if kb:
                                name = str(kb)
                        except Exception:
                            pass

                        OrderLineItem.objects.create(
                            order=order,
                            product_name=name,
                            quantity=qty,
                            price=price,
                        )
                        total += price * qty

                    # clear session basket
                    if request.session.get('basket'):
                        del request.session['basket']
                        request.session.modified = True

                # persist computed total
                order.total = total
                order.save()

            # Order created — render the checkout page again but now
            # show the payment form for the created order so the user
            # can enter card details and complete payment.
            payment_required = True
            # Build summary from the created order's line items
            summary_items = []
            summary_total = Decimal('0.00')
            for li in order.items.all():
                qty = int(li.quantity)
                price = Decimal(li.price)
                subtotal = price * qty
                summary_items.append(
                    {
                        'name': li.product_name,
                        'quantity': qty,
                        'unit_price': price,
                        'subtotal': subtotal,
                    }
                )
                summary_total += subtotal

            context = {
                'form': form,
                'summary_items': summary_items,
                'summary_total': summary_total,
                'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
                'payment_required': True,
                'order': order,
            }
            return render(request, 'checkout/checkout.html', context)
        messages.error(request, 'Please correct the errors below')
    else:
        # Prefill form from authenticated user's profile when available
        if request.user.is_authenticated:
            try:
                profile = request.user.userprofile
            except Exception:
                profile = None

            initial = {
                'full_name': request.user.get_full_name() or '',
                'email': request.user.email or '',
                'phone_number': getattr(profile, 'default_phone_number', '') or '',
                'street_address1': getattr(profile, 'default_street_address1', '') or '',
                'street_address2': getattr(profile, 'default_street_address2', '') or '',
                'town_or_city': getattr(profile, 'default_town_or_city', '') or '',
                'postcode': getattr(profile, 'default_postcode', '') or '',
                'county': getattr(profile, 'default_county', '') or '',
                'country': getattr(profile, 'default_country', '') or '',
            }
            form = OrderForm(initial=initial)
        else:
            form = OrderForm()

    # Build an order summary (for display beside the form)
    summary_items = []
    summary_total = Decimal('0.00')
    if request.user.is_authenticated:
        basket_obj, _ = Basket.objects.get_or_create(user=request.user)
        for it in basket_obj.items.select_related('content_type'):
            qty = int(it.quantity)
            price = Decimal(it.price_snapshot)
            subtotal = price * qty
            summary_items.append(
                {
                    'name': str(it.content_object),
                    'quantity': qty,
                    'unit_price': price,
                    'subtotal': subtotal,
                }
            )
            summary_total += subtotal
    else:
        session_basket = request.session.get('basket', {})
        for weight_str, data in (session_basket or {}).items():
            qty = int(data.get('quantity', 0))
            try:
                price = Decimal(str(data.get('price_gbp', '0')))
            except InvalidOperation:
                price = Decimal('0.00')
            subtotal = price * qty
            # try to find product label
            label = f"{weight_str} kg kettlebell"
            try:
                w = Decimal(str(weight_str))
                kb = Kettlebell.objects.filter(
                    weight=w, weight_unit='kg'
                ).first()
                if kb:
                    label = str(kb)
            except Exception:
                pass

            summary_items.append(
                {
                    'name': label,
                    'quantity': qty,
                    'unit_price': price,
                    'subtotal': subtotal,
                }
            )
            summary_total += subtotal

    context = {
        'form': form,
        'summary_items': summary_items,
        'summary_total': summary_total,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    }
    return render(request, 'checkout/checkout.html', context)


def checkout_success(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    return render(
        request,
        'checkout/checkout_success.html',
        {'order': order},
    )


@require_POST
def cache_checkout_data(request):
    # Placeholder endpoint used by front-end to cache data before payment
    try:
        data = json.loads(request.body.decode('utf-8'))
        # For now, just record into session for debugging
        request.session['checkout_cache'] = data
        request.session.modified = True
        return render(request, 'checkout/cache_ok.html')
    except Exception:
        return render(request, 'checkout/cache_fail.html')
