from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Basket, BasketItem
from django.views.decorators.http import require_POST
import json
from kettlebell_shop.models import Kettlebell


def _session_basket_to_list(session_basket):
    items = []
    for weight_str, data in (session_basket or {}).items():
        items.append(
            {
                "weight": weight_str,
                "quantity": data.get("quantity"),
                "price_gbp": data.get("price_gbp"),
            }
        )
    return items


def view_basket(request):
    if request.user.is_authenticated:
        basket_obj, _ = Basket.objects.get_or_create(user=request.user)
        items = []
        for it in basket_obj.items.select_related("content_type"):
            items.append(
                {
                    "id": it.id,
                    "label": str(it.content_object),
                    "quantity": it.quantity,
                    "price": it.price_snapshot,
                }
            )
        return render(request, "basket/view.html", {"items": items})
    else:
        session_basket = request.session.get("basket", {})
        items = _session_basket_to_list(session_basket)
        return render(request, "basket/view.html", {"items": items})


@login_required
def update_item(request, item_id):
    item = get_object_or_404(BasketItem, id=item_id, basket__user=request.user)
    if request.method == "POST":
        qty = int(request.POST.get("quantity", 0))
        if qty <= 0:
            item.delete()
        else:
            item.quantity = qty
            item.save()
    return redirect("basket:view")


def basket_api(request):
    """Return JSON with basket contents and total count for header."""
    if request.user.is_authenticated:
        basket_obj, _ = Basket.objects.get_or_create(user=request.user)
        total_items = sum(it.quantity for it in basket_obj.items.all())
    else:
        session_basket = request.session.get("basket", {})
        total_items = sum(
            int(v.get("quantity", 0)) for v in session_basket.values()
        )
    return JsonResponse({"count": total_items})


def clear_merge_flag(request):
    # Called by frontend to clear the session 'basket_merged' flag
    # after showing toast
    if request.session.get("basket_merged"):
        del request.session["basket_merged"]
        request.session.modified = True
    return JsonResponse({"ok": True})


def basket_contents_api(request):
    """Return full basket contents (items, quantities, per-item totals
    and grand total).
    """
    items = []
    grand_total = 0
    if request.user.is_authenticated:
        basket_obj, _ = Basket.objects.get_or_create(user=request.user)
        for it in basket_obj.items.select_related('content_type'):
            subtotal = float(it.price_snapshot) * it.quantity
            # try to include stock and weight when content_object provides them
            product = None
            try:
                product = it.content_object
            except Exception:
                product = None

            items.append({
                'id': it.id,
                'label': str(it.content_object),
                'quantity': it.quantity,
                'price': float(it.price_snapshot),
                'subtotal': round(subtotal, 2),
                'stock': getattr(product, 'stock', None),
                'weight': getattr(product, 'weight', None),
            })
            grand_total += subtotal
    else:
        session_basket = request.session.get('basket', {})
        for weight_str, data in session_basket.items():
            qty = int(data.get('quantity', 0))
            price = float(data.get('price_gbp', 0))
            subtotal = price * qty
            # attempt to find product by weight to expose stock
            try:
                kb = Kettlebell.objects.get(weight=int(weight_str))
                stock = kb.stock
            except Exception:
                stock = None

            items.append(
                {
                    'weight': weight_str,
                    'label': f"{weight_str} kg kettlebell",
                    'quantity': qty,
                    'price': price,
                    'subtotal': round(subtotal, 2),
                    'stock': stock,
                }
            )
            grand_total += subtotal

    # also include total item count for convenience
    total_count = sum(it.get('quantity', 0) for it in items)
    return JsonResponse(
        {
            'items': items,
            'grand_total': round(grand_total, 2),
            'count': total_count,
        }
    )


@require_POST
def clear_basket_api(request):
    """Clear the entire basket for the current user or session.

    Returns the same structure as `basket_contents_api` (empty contents).
    """
    if request.user.is_authenticated:
        basket_obj, _ = Basket.objects.get_or_create(user=request.user)
        # delete all BasketItem rows for this basket
        basket_obj.items.all().delete()
    else:
        # clear session basket
        if request.session.get('basket'):
            del request.session['basket']
            request.session.modified = True

    return basket_contents_api(request)


@require_POST
def basket_update_api(request):
    """AJAX endpoint to update quantity or remove an item. Accepts JSON body.

    For authenticated items send {item_id, quantity}.
    For anonymous session items send {weight, quantity}.
    Returns updated basket contents via basket_contents_api format.
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        payload = request.POST.dict()

    # Authenticated users: update BasketItem by id
    if request.user.is_authenticated and payload.get('item_id'):
        item_id = int(payload.get('item_id'))
        qty = int(payload.get('quantity', 0))
        item = get_object_or_404(
            BasketItem, id=item_id, basket__user=request.user
        )
        # Validate stock using the underlying product if possible
        product = None
        try:
            product = item.content_object
        except Exception:
            product = None

        if qty <= 0:
            item.delete()
        else:
            if product and hasattr(product, 'stock') and qty > product.stock:
                return JsonResponse(
                    {'ok': False, 'error': 'Requested quantity exceeds stock'},
                    status=400,
                )
            item.quantity = qty
            item.save()
    else:
        # session-based update
        weight = payload.get('weight')
        qty = int(payload.get('quantity', 0))
        session_basket = request.session.get('basket', {})
        if not weight or weight not in session_basket:
            return JsonResponse({'error': 'not found'}, status=404)
    # Validate stock for anonymous items by looking up the kettlebell
    # by weight
        try:
            kb = Kettlebell.objects.get(weight=int(weight))
        except Kettlebell.DoesNotExist:
            kb = None

        if qty <= 0:
            session_basket.pop(weight, None)
        else:
            if kb and qty > kb.stock:
                return JsonResponse(
                    {'ok': False, 'error': 'Requested quantity exceeds stock'},
                    status=400,
                )
            session_basket[weight]['quantity'] = qty
        request.session['basket'] = session_basket
        request.session.modified = True

    # return updated contents including count and grand_total
    return basket_contents_api(request)
