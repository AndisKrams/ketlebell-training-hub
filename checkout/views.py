import json

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages

from .forms import OrderForm
from .models import Order


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
            # Store some basket snapshot if needed (placeholder)
            order.original_basket = json.dumps(
                request.session.get('basket', {})
            )
            order.total = 0
            order.save()
            messages.success(request, 'Order placed successfully')
            return redirect(
                'checkout:checkout_success',
                order_number=order.order_number,
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
