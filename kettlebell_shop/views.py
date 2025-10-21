
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Kettlebell
# ContentType will be imported locally only when needed
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
        from decimal import Decimal, InvalidOperation

        data = json.loads(request.body)
        weight_raw = data.get('weight')
        unit = data.get('unit', 'kg')
        try:
            weight = Decimal(str(weight_raw))
        except (InvalidOperation, TypeError):
            return HttpResponseBadRequest('Invalid weight')

        quantity = int(data.get('quantity'))
    except Exception:
        return HttpResponseBadRequest('Invalid payload')

    if quantity < 1:
        return JsonResponse(
            {'ok': False, 'error': 'Quantity must be at least 1'}
        )

    # Normalize a key for session storage (strip trailing zeros)
    weight_str = str(weight)
    if '.' in weight_str:
        weight_key = weight_str.rstrip('0').rstrip('.')
    else:
        weight_key = weight_str
    # Existing amount in session (anonymous side)
    basket = request.session.get('basket', {})
    key = weight_key
    existing_session_qty = int(basket.get(key, {}).get('quantity', 0))

    # If authenticated, use a DB transaction + select_for_update to avoid
    # race conditions where two concurrent requests could both pass the
    # availability check and oversubscribe stock.
    if request.user.is_authenticated:
        from django.contrib.contenttypes.models import ContentType

        try:
            with transaction.atomic():
                # lock the product row to get latest stock
                # look up by numeric weight and unit
                product = (
                    Kettlebell.objects.select_for_update().get(
                        weight=weight, weight_unit=unit
                    )
                )

                basket_obj, _ = (
                    Basket.objects.select_for_update().get_or_create(
                        user=request.user
                    )
                )

                ct = ContentType.objects.get_for_model(product)
                existing_item = (
                    BasketItem.objects.select_for_update()
                    .filter(
                        basket=basket_obj,
                        content_type=ct,
                        object_id=product.id,
                    )
                    .first()
                )

                if existing_item:
                    existing_db_qty = int(existing_item.quantity)
                else:
                    existing_db_qty = 0

                total_after = (
                    existing_session_qty + existing_db_qty + quantity
                )
                if total_after > product.stock:
                    return JsonResponse(
                        {
                            'ok': False,
                            'error': 'Requested quantity exceeds stock',
                        }
                    )

                # Update session to reflect the new quantity for consistency
                new_session_qty = existing_session_qty + quantity
                basket = request.session.get('basket', {})
                basket[key] = {
                    'quantity': new_session_qty,
                    'price_gbp': str(product.price_gbp),
                }
                request.session['basket'] = basket
                request.session.modified = True

                # Persist into DB (create or increment)
                if existing_item:
                    existing_item.quantity = existing_item.quantity + quantity
                    existing_item.price_snapshot = product.price_gbp
                    existing_item.save()
                else:
                    BasketItem.objects.create(
                        basket=basket_obj,
                        content_type=ct,
                        object_id=product.id,
                        quantity=quantity,
                        price_snapshot=product.price_gbp,
                    )

        except Kettlebell.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Product not found'})
        except Exception:
            # Fallback: return a generic error to avoid exposing internals
            return JsonResponse(
                {'ok': False, 'error': 'Could not add to basket'}
            )

        # compute totals from session for UI
        session_basket = request.session.get('basket', {})
        grand_total = 0
        total_count = 0
        try:
            for w_str, d in session_basket.items():
                total_count += int(d.get('quantity', 0))
                grand_total += (
                    float(d.get('price_gbp', 0)) * int(d.get('quantity', 0))
                )
        except Exception:
            pass

        remaining_stock = product.stock - (existing_db_qty + new_session_qty)
        return JsonResponse(
            {
                'ok': True,
                'basket': request.session.get('basket', {}),
                'grand_total': round(grand_total, 2),
                'count': total_count,
                'remaining_stock': remaining_stock,
            }
        )

    # Anonymous (session-backed) flow: re-fetch product to ensure latest stock
    product = get_object_or_404(
        Kettlebell, weight=weight, weight_unit=unit
    )
    existing_db_qty = 0
    total_after = existing_session_qty + existing_db_qty + quantity
    if total_after > product.stock:
        return JsonResponse(
            {'ok': False, 'error': 'Requested quantity exceeds stock'}
        )

    # Update session basket
    basket = request.session.get('basket', {})
    existing = basket.get(
        key, {'quantity': 0, 'price_gbp': str(product.price_gbp)}
    )
    existing['quantity'] = existing.get('quantity', 0) + quantity
    existing['price_gbp'] = str(product.price_gbp)
    basket[key] = existing
    request.session['basket'] = basket
    request.session.modified = True

    # for anonymous users, compute totals similarly
    session_basket = request.session.get('basket', {})
    grand_total = 0
    total_count = 0
    try:
        for w_str, d in session_basket.items():
            total_count += int(d.get('quantity', 0))
            grand_total += (
                float(d.get('price_gbp', 0)) * int(d.get('quantity', 0))
            )
    except Exception:
        pass

    remaining_stock = (
        product.stock
        - (
            existing_db_qty + int(basket.get(key, {}).get('quantity', 0))
        )
    )
    return JsonResponse(
        {
            'ok': True,
            'basket': basket,
            'grand_total': round(grand_total, 2),
            'count': total_count,
            'remaining_stock': remaining_stock,
        }
    )
