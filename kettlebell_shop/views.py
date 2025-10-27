
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Kettlebell
from decimal import Decimal, InvalidOperation
import logging
# ContentType will be imported locally only when needed
from basket.models import Basket, BasketItem

logger = logging.getLogger(__name__)


def shop_view(request):
    kettlebells_qs = Kettlebell.objects.all().order_by('weight')

    # Build session snapshot (anonymous basket entries)
    session_basket = request.session.get('basket', {})

    def _weight_key(weight):
        # normalize weight into same string key used by add_to_basket
        s = str(weight)
        if '.' in s:
            return s.rstrip('0').rstrip('.')
        return s

    kettlebells = []
    # Import ContentType here to avoid module-level dependency
    from django.contrib.contenttypes.models import ContentType

    for kb in kettlebells_qs:
        key = _weight_key(kb.weight)
        session_qty = int(session_basket.get(key, {}).get('quantity', 0))

        db_qty = 0
        if request.user.is_authenticated:
            try:
                ct = ContentType.objects.get_for_model(kb)
                basket_obj = Basket.objects.filter(user=request.user).first()
                if basket_obj:
                    bi = BasketItem.objects.filter(
                        basket=basket_obj,
                        content_type=ct,
                        object_id=kb.id,
                    ).first()
                    if bi:
                        db_qty = int(bi.quantity)
            except Exception:
                db_qty = 0

        available = kb.stock - (db_qty + session_qty)
        if available < 0:
            available = 0

        kettlebells.append({'product': kb, 'available_stock': available})

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
                # If the session holds a stale reservation (session has qty
                # but DB has none) it's possible a checkout/clear route
                # removed DB items but left the session entry. In that
                # case, if the product.stock alone can satisfy the requested
                # quantity, drop the stale session entry and continue.
                if total_after > product.stock:
                    if existing_db_qty == 0 and existing_session_qty > 0:
                        # if the bare product stock can satisfy the request
                        if product.stock >= quantity:
                            try:
                                logger.info(
                                    'add_to_basket: removing stale session entry -> '
                                    'user=%s product_id=%s weight=%s '
                                    'session_before=%s',
                                    getattr(request.user, 'pk', None),
                                    getattr(product, 'id', None),
                                    str(weight),
                                    request.session.get('basket', {}),
                                )
                            except Exception:
                                logger.exception('add_to_basket: failed to log stale session removal')

                            # remove stale key and recalc
                            try:
                                basket = request.session.get('basket', {})
                                basket.pop(key, None)
                                request.session['basket'] = basket
                                request.session.modified = True
                                existing_session_qty = 0
                                total_after = existing_db_qty + quantity
                            except Exception:
                                logger.exception('add_to_basket: error clearing stale session key')
                        else:
                            # can't satisfy even with stale removal; fall through
                            pass

                if total_after > product.stock:
                    # Log diagnostics to help track down stale reservations
                    try:
                        logger.warning(
                            'add_to_basket: requested quantity exceeds stock | '
                            'user=%s product_id=%s weight=%s stock=%s '
                            'existing_db_qty=%s existing_session_qty=%s '
                            'requested=%s total_after=%s '
                            'session_snapshot=%s',
                            getattr(request.user, 'pk', None),
                            getattr(product, 'id', None),
                            str(weight),
                            getattr(product, 'stock', None),
                            existing_db_qty,
                            existing_session_qty,
                            quantity,
                            total_after,
                            request.session.get('basket', {}),
                        )
                    except Exception:
                        # Ensure logging never raises
                        logger.exception(
                            'add_to_basket: failed to log diagnostics'
                        )

                    # Keep the client response unchanged to avoid leaking internals
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
            logger.warning(
                'add_to_basket: product not found | user=%s weight=%s unit=%s',
                getattr(request.user, 'pk', None),
                weight_raw,
                unit,
            )
            return JsonResponse({'ok': False, 'error': 'Product not found'})
        except Exception:
            # Log the stack trace for debugging, then return a generic error
            logger.exception(
                'add_to_basket: unexpected exception while adding to basket'
            )
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
        try:
            logger.warning(
                'add_to_basket(anon): requested quantity exceeds stock | '
                'user=None product_id=%s weight=%s stock=%s '
                'existing_db_qty=%s existing_session_qty=%s requested=%s '
                'total_after=%s session_snapshot=%s',
                getattr(product, 'id', None),
                str(weight),
                getattr(product, 'stock', None),
                existing_db_qty,
                existing_session_qty,
                quantity,
                total_after,
                request.session.get('basket', {}),
            )
        except Exception:
            logger.exception('add_to_basket: failed to log anon diagnostics')

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
