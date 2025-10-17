from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Basket, BasketItem


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
        total_items = sum(int(v.get("quantity", 0)) for v in session_basket.values())
    return JsonResponse({"count": total_items})


def clear_merge_flag(request):
    # Called by frontend to clear the session 'basket_merged' flag after showing toast
    if request.session.get("basket_merged"):
        del request.session["basket_merged"]
        request.session.modified = True
    return JsonResponse({"ok": True})
