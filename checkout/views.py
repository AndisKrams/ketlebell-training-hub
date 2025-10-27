import json
from decimal import Decimal, InvalidOperation
from collections import OrderedDict

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse
from .forms import OrderForm
from .models import Order, OrderLineItem
from basket.models import Basket
from kettlebell_shop.models import Kettlebell
from django.views.decorators.http import require_POST


@require_POST
def mark_order_paid(request, order_number):
    """Mark the given order as paid.

    This endpoint is called by the client after a successful
    confirmCardPayment to update order state immediately for UX.
    It is idempotent and also protected by ownership checks: the
    authenticated user must own the order, or the session must
    contain the matching pending_order_number for anonymous users.
    """
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Order not found'}, status=404)

    # ownership / session check
    if request.user.is_authenticated:
        try:
            if not order.profile or order.profile.user != request.user:
                return JsonResponse({'ok': False, 'error': 'Permission denied'}, status=403)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Permission check failed'}, status=403)
    else:
        pending = request.session.get('pending_order_number')
        if not pending or pending != order_number:
            return JsonResponse({'ok': False, 'error': 'Permission denied'}, status=403)

    # mark paid and status
    order.paid = True
    order.status = Order.STATUS_PAID
    order.save()

    # clear pending marker from session
    if request.session.get('pending_order_number') == order_number:
        del request.session['pending_order_number']
        request.session.modified = True

    # clear DB basket if owned
    try:
        if request.user.is_authenticated and order.profile and order.profile.user == request.user:
            try:
                basket_obj = Basket.objects.get(user=request.user)
                basket_obj.items.all().delete()
            except Basket.DoesNotExist:
                pass
    except Exception:
        pass

    return JsonResponse({'ok': True})


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

    qs = Order.objects.select_related('profile').prefetch_related('items')
    order = get_object_or_404(qs, order_number=order_number)

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


def _aggregate_order_items(items_iterable):
    """Aggregate an iterable of OrderLineItem objects by product name
    and unit price, summing quantities. Returns a list of dicts with
    keys: name, unit_price (Decimal), quantity (int), subtotal (Decimal).
    """
    groups = OrderedDict()
    for li in items_iterable:
        try:
            name = li.product_name
            unit_price = Decimal(li.price)
            qty = int(li.quantity)
        except Exception:
            # Skip malformed line items
            continue
        key = (name, str(unit_price))
        if key not in groups:
            groups[key] = {'name': name, 'unit_price': unit_price, 'quantity': qty}
        else:
            groups[key]['quantity'] += qty

    result = []
    for v in groups.values():
        subtotal = v['unit_price'] * v['quantity']
        # Provide both new keys and legacy keys for templates
        result.append(
            {
                'name': v['name'],
                'product_name': v['name'],
                'unit_price': v['unit_price'],
                'price': v['unit_price'],
                'quantity': v['quantity'],
                'subtotal': subtotal,
            }
        )
    return result


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

    qs = Order.objects.select_related('profile').prefetch_related('items')
    order = get_object_or_404(qs, order_number=order_number)

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
                return JsonResponse(
                    {'error': f'Could not create customer: {e}'}, status=500
                )

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
        return JsonResponse(
            {'error': f'Could not create payment intent: {e}'}, status=500
        )

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
            # If the user (or session) already has a pending order for
            # the current basket, reuse it to avoid duplicate unpaid
            # orders. For authenticated users prefer matching by
            # `profile`, for anonymous users track pending order in
            # session.
            order = form.save(commit=False)
            existing_order = None
            if request.user.is_authenticated:
                try:
                    profile = request.user.userprofile
                    existing_order = (
                        Order.objects.filter(
                            profile=profile, status=Order.STATUS_PENDING
                        )
                        .order_by('-date')
                        .first()
                    )
                    # only reuse if original_basket matches current basket
                    if existing_order:
                        try:
                            cur = json.dumps(
                                request.session.get('basket', {})
                            )
                            if (existing_order.original_basket or '') != cur:
                                existing_order = None
                        except Exception:
                            existing_order = None
                except Exception:
                    existing_order = None
            else:
                pending_number = request.session.get('pending_order_number')
                if pending_number:
                    try:
                        tmp = Order.objects.filter(
                            order_number=pending_number,
                            status=Order.STATUS_PENDING,
                        ).first()
                        if tmp:
                            # check basket match
                            try:
                                cur = json.dumps(
                                    request.session.get('basket', {})
                                )
                                if (tmp.original_basket or '') == cur:
                                    existing_order = tmp
                            except Exception:
                                existing_order = None
                    except Exception:
                        existing_order = None

            if existing_order:
                # reuse existing order; update contact fields
                order = existing_order
                order.full_name = form.cleaned_data.get('full_name')
                order.email = form.cleaned_data.get('email')
                order.phone_number = form.cleaned_data.get('phone_number')
                order.street_address1 = (
                    form.cleaned_data.get('street_address1')
                )
                order.street_address2 = (
                    form.cleaned_data.get('street_address2')
                )
                order.town_or_city = form.cleaned_data.get('town_or_city')
                order.postcode = form.cleaned_data.get('postcode')
                order.county = form.cleaned_data.get('county')
            
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
            # Remember if we're reusing an existing pending order so we can
            # clear pre-existing line items before recreating them. This
            # prevents duplicate OrderLineItem rows when a pending order
            # is reused (e.g. user resubmits the checkout form).
            reused_order = True if existing_order else False

            with transaction.atomic():
                order.save()  # generate order_number via model save

                # If reusing an existing order, remove any previously
                # created line items so we can recreate a fresh snapshot.
                if reused_order:
                    try:
                        order.items.all().delete()
                    except Exception:
                        pass

                total = Decimal('0.00')

                # Authenticated users: copy from BasketItem objects
                if request.user.is_authenticated:
                    basket_obj, _ = Basket.objects.get_or_create(
                        user=request.user
                    )
                    # Collect unsaved OrderLineItem instances and bulk create
                    items_to_create = []
                    for it in basket_obj.items.select_related('content_type'):
                        qty = int(it.quantity)
                        price = Decimal(it.price_snapshot)
                        name = str(it.content_object)
                        items_to_create.append(
                            OrderLineItem(
                                order=order,
                                product_name=name,
                                quantity=qty,
                                price=price,
                            )
                        )
                        total += price * qty
                    if items_to_create:
                        OrderLineItem.objects.bulk_create(items_to_create)
                    # Do not clear the DB basket here. Keep items in
                    # the user's basket until payment completes so the user
                    # can recover or retry payment. Will clear the basket
                    # after successful payment in `checkout_success` or via
                    # webhook handling.
                else:
                    # Session-based anonymous basket format:
                    # {weight_str: {quantity, price_gbp}}
                    session_basket = request.session.get('basket', {})
                    # For anonymous/session basket build items and bulk create
                    items_to_create = []
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

                        items_to_create.append(
                            OrderLineItem(
                                order=order,
                                product_name=name,
                                quantity=qty,
                                price=price,
                            )
                        )
                        total += price * qty
                    if items_to_create:
                        OrderLineItem.objects.bulk_create(items_to_create)

                        # Do not clear the session basket here. Keep the
                        # anonymous user's basket in session until payment
                        # completes; we'll clear it on `checkout_success` when
                        # the user returns after payment.

                # persist computed total
                order.total = total
                order.save()

            # Order created — render the checkout page again but now
            # show the payment form for the created order so the user
            # can enter card details and complete payment.
            # Build summary from the created order's line items
            # Aggregate duplicate line items for display (combine same product & price)
            summary_items = _aggregate_order_items(order.items.all())
            summary_total = sum((x['subtotal'] for x in summary_items), Decimal('0.00'))

            context = {
                'form': form,
                'summary_items': summary_items,
                'summary_total': summary_total,
                'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
                'payment_required': True,
                'order': order,
            }
            # Mark pending order in session so anonymous users can later
            # cancel it. Also harmless for authenticated users.
            try:
                request.session['pending_order_number'] = order.order_number
                request.session.modified = True
            except Exception:
                pass
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
                'phone_number': (
                    getattr(profile, 'default_phone_number', '') or ''
                ),
                'street_address1': (
                    getattr(profile, 'default_street_address1', '') or ''
                ),
                'street_address2': (
                    getattr(profile, 'default_street_address2', '') or ''
                ),
                'town_or_city': (
                    getattr(profile, 'default_town_or_city', '') or ''
                ),
                'postcode': (
                    getattr(profile, 'default_postcode', '') or ''
                ),
                'county': (
                    getattr(profile, 'default_county', '') or ''
                ),
                'country': (
                    getattr(profile, 'default_country', '') or ''
                ),
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


def resume_checkout(request, order_number):
    """Render the checkout/payment form for an existing pending order.

    Ownership: authenticated user must own the order, or anonymous users
    must have the matching pending_order_number in session.
    """
    qs = Order.objects.select_related('profile').prefetch_related('items')
    order = get_object_or_404(qs, order_number=order_number)

    # Ownership / session check
    if request.user.is_authenticated:
        try:
            if not order.profile or order.profile.user != request.user:
                messages.error(request, 'You do not have permission to complete this order')
                return redirect('profiles:profile')
        except Exception:
            messages.error(request, 'Could not verify order ownership')
            return redirect('profiles:profile')
    else:
        pending = request.session.get('pending_order_number')
        if not pending or pending != order_number:
            messages.error(request, 'You do not have permission to complete this order')
            return redirect('checkout:checkout')

    # Only pending orders may be completed here
    if order.status != Order.STATUS_PENDING:
        messages.error(request, 'Only pending orders can be completed')
        return redirect('profiles:profile' if request.user.is_authenticated else 'checkout:checkout')

    # Build aggregated summary items from order line items (combine duplicates)
    summary_items = _aggregate_order_items(order.items.all())
    summary_total = sum((x['subtotal'] for x in summary_items), Decimal('0.00'))

    # Mark pending order in session for anonymous users
    try:
        request.session['pending_order_number'] = order.order_number
        request.session.modified = True
    except Exception:
        pass

    context = {
        'form': None,
        'summary_items': summary_items,
        'summary_total': summary_total,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
        'payment_required': True,
        'order': order,
    }
    return render(request, 'checkout/checkout.html', context)


def order_detail(request, order_number):
    """Show a minimal order detail page.

    Only the order owner or staff users may view the page.
    If the `contact` app is present, show any contact messages
    associated with the order.
    """
    qs = Order.objects.select_related('profile').prefetch_related('items')
    order = get_object_or_404(qs, order_number=order_number)

    # Ownership check: owner or staff may view
    if request.user.is_authenticated:
        try:
            is_owner = order.profile and order.profile.user == request.user
        except Exception:
            is_owner = False
        if not (is_owner or request.user.is_staff):
            messages.error(request, 'You do not have permission to view that order')
            return redirect('profiles:profile')
    else:
        # disallow anonymous access to order details
        messages.error(request, 'You must be signed in to view order details')
        return redirect('profiles:profile')

    # Gather aggregated line items and optional contact messages
    items = _aggregate_order_items(order.items.all())
    contact_messages = []
    try:
        from contact.models import ContactMessage

        contact_messages = list(ContactMessage.objects.filter(order=order).order_by('-created'))
    except Exception:
        contact_messages = []

    return render(
        request,
        'checkout/order_detail.html',
        {'order': order, 'items': items, 'contact_messages': contact_messages},
    )


def checkout_success(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    # If the user returned here after a successful payment, clear their
    # basket. For authenticated users we can clear the DB basket. For
    # anonymous users we compare the saved original_basket to the current
    # session basket and clear the session if they match.
    try:
        if request.user.is_authenticated:
            # only clear if the order belongs to this user
            if order.profile and order.profile.user == request.user:
                try:
                    basket_obj = Basket.objects.get(user=request.user)
                    basket_obj.items.all().delete()
                except Basket.DoesNotExist:
                    pass
        else:
            try:
                orig = json.loads(order.original_basket or '{}')
                if orig and orig == request.session.get('basket', {}):
                    if 'basket' in request.session:
                        del request.session['basket']
                        request.session.modified = True
            except Exception:
                # if parsing fails or other error occurs we won't clear
                # the session to avoid data loss
                pass
    except Exception:
        # swallow any unexpected errors during cleanup so the success
        # page still renders for the user
        pass

    # Provide aggregated items for the success page as well
    items = _aggregate_order_items(order.items.all())
    return render(request, 'checkout/checkout_success.html', {'order': order, 'items': items})


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


@require_POST
def cancel_order(request, order_number):
    """Cancel a pending order.

    For authenticated users the order must belong to the user's profile.
    For anonymous users, the order_number must match the session's
    pending_order_number. Only orders with STATUS_PENDING will be
    cancelled (marked as STATUS_FAILED) to preserve audit trail.
    """
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        messages.error(request, 'Order not found')
        return redirect('checkout:checkout')

    # only allow cancelling pending orders
    if order.status != Order.STATUS_PENDING:
        messages.error(request, 'Only pending orders can be cancelled')
        return redirect('profiles:profile' if request.user.is_authenticated else 'checkout:checkout')

    # Authenticated user: ensure order belongs to them
    if request.user.is_authenticated:
        try:
            if not order.profile or order.profile.user != request.user:
                messages.error(request, 'You do not have permission to cancel this order')
                return redirect('profiles:profile')
        except Exception:
            messages.error(request, 'Could not verify order ownership')
            return redirect('profiles:profile')
    else:
        # Anonymous: check pending number in session
        pending = request.session.get('pending_order_number')
        if not pending or pending != order_number:
            messages.error(request, 'You do not have permission to cancel this order')
            return redirect('checkout:checkout')

    # Mark order as failed (cancelled) and clear any session marker
    order.status = Order.STATUS_FAILED
    order.paid = False
    order.save()

    # clear pending_order_number from session if it matches
    if request.session.get('pending_order_number') == order_number:
        del request.session['pending_order_number']
        request.session.modified = True

    # If this order was created from the user's basket, clear that
    # basket so the held quantities are released back to stock. For
    # authenticated users we can clear the DB basket. For anonymous
    # users clear the session basket only when it matches the
    # order.original_basket to avoid removing unrelated items.
    try:
        if request.user.is_authenticated:
            if order.profile and order.profile.user == request.user:
                try:
                    basket_obj = Basket.objects.get(user=request.user)
                    basket_obj.items.all().delete()
                except Basket.DoesNotExist:
                    pass
        else:
            # Clear the session basket for anonymous users so held
            # quantities are released. We clear unconditionally because
            # the session belongs to the user who created the pending
            # order (we already verified pending_order_number earlier).
            try:
                if 'basket' in request.session:
                    del request.session['basket']
                    request.session.modified = True
            except Exception:
                pass
    except Exception:
        # don't block the cancel flow on cleanup errors
        pass

    messages.success(request, 'Pending order cancelled')
    return redirect('profiles:profile' if request.user.is_authenticated else 'checkout:checkout')
