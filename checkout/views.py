import json
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction

from .forms import OrderForm
from .models import Order, OrderLineItem
from basket.models import Basket
from kettlebell_shop.models import Kettlebell


def checkout(request):
    """Simple checkout view: shows form and creates an Order.

    This implementation expects a server-side basket retrieval.
    """
    # For this minimal implementation don't integrate Stripe;
    # just create an Order from posted form data and redirect to
    # success.
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

            messages.success(request, 'Order placed successfully')
            return redirect(
                'checkout:checkout_success', order_number=order.order_number
            )
        messages.error(request, 'Please correct the errors below')
    else:
        form = OrderForm()

    return render(request, 'checkout/checkout.html', {'form': form})


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
