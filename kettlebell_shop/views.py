
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from .models import Kettlebell
from django.contrib.contenttypes.models import ContentType
from basket.models import Basket, BasketItem


def shop_view(request):
    kettlebells = Kettlebell.objects.all().order_by('weight')
    return render(
        request,
        'kettlebell_shop/shop.html',
        {'kettlebells': kettlebells},
    )


@require_POST
def add_to_basket(request):
    """AJAX endpoint to add a kettlebell to the session basket.

    Expects JSON body: {"weight": 16, "quantity": 2}
    Returns JSON with success or error message and current basket.
    """
    try:
        import json

        data = json.loads(request.body)
        weight = int(data.get('weight'))
        quantity = int(data.get('quantity'))
    except Exception:
        return HttpResponseBadRequest('Invalid payload')

    product = get_object_or_404(Kettlebell, weight=weight)
    if quantity < 1:
        return JsonResponse(
            {'ok': False, 'error': 'Quantity must be at least 1'}
        )
    if quantity > product.stock:
        return JsonResponse(
            {'ok': False, 'error': 'Requested quantity exceeds stock'}
        )

    basket = request.session.get('basket', {})
    key = str(product.weight)
    existing = basket.get(
        key,
        {
            'quantity': 0,
            'price_gbp': str(product.price_gbp),
        },
    )
    existing['quantity'] = existing.get('quantity', 0) + quantity
    existing['price_gbp'] = str(product.price_gbp)
    basket[key] = existing
    request.session['basket'] = basket
    request.session.modified = True

    # If user is authenticated, persist into DB
    if request.user.is_authenticated:
        basket_obj, _ = Basket.objects.get_or_create(user=request.user)
        ct = ContentType.objects.get_for_model(product)
        item, created = BasketItem.objects.get_or_create(
            basket=basket_obj,
            content_type=ct,
            object_id=product.id,
            defaults={
                'quantity': quantity,
                'price_snapshot': product.price_gbp,
            },
        )
        if not created:
            item.quantity = item.quantity + quantity
            item.price_snapshot = product.price_gbp
            item.save()

    return JsonResponse({'ok': True, 'basket': basket})
