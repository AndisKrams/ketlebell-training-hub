import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction

from kettlebell_shop.models import Kettlebell

logger = logging.getLogger(__name__)


def _parse_weight_unit_from_name(name):
    """Attempt to parse a numeric weight and unit from a product_name string.

    Expected formats (best-effort):
    - "48 kg (£82.00)"
    - "48 kg kettlebell"
    - "48 kg (Fancy)"
    Returns (Decimal weight, unit) or (None, None) if not parsable.
    """
    try:
        parts = name.split()
        if not parts:
            return None, None
        # first token should be numeric weight
        w = parts[0]
        weight = Decimal(str(w))
        unit = 'kg'
        if len(parts) > 1 and parts[1] in ('kg', 'lb'):
            unit = parts[1]
        return weight, unit
    except (InvalidOperation, Exception):
        return None, None


def apply_order_stock_adjustment(order):
    """Apply stock decrements for the given order's line items.

    This is best-effort: for each OrderLineItem we try to locate a
    matching Kettlebell product (by parsing the product_name) and
    decrement its `stock` by the line item quantity. The operation is
    performed inside a transaction and uses `select_for_update` on the
    product row to avoid races.

    The function is idempotent when called only when the order's status
    transitions from non-paid to paid (the callers should enforce that),
    which prevents double-decrements from duplicate webhooks.
    """
    if not order:
        return

    # If we've already applied stock adjustments for this order, skip.
    try:
        if getattr(order, 'stock_adjusted', False):
            logger.info(
                'Stock adjust: already applied for order %s',
                order.order_number,
            )
            return
    except Exception:
        # If the attribute isn't present (older DB state), continue and
        # allow the migration to set the field later.
        pass

    with transaction.atomic():
        # select_related product to avoid extra queries when present
        for li in order.items.select_related('product'):
            qty = int(li.quantity or 0)
            if qty <= 0:
                continue

            kb = None
            # Prefer explicit FK when available
            if getattr(li, 'product', None) is not None:
                try:
                    kb = (
                        Kettlebell.objects.select_for_update()
                        .filter(pk=li.product_id)
                        .first()
                    )
                except Exception:
                    kb = None

            # Fallback to parsing product_name for older rows
            if kb is None:
                name = (li.product_name or '').strip()
                weight, unit = _parse_weight_unit_from_name(name)
                if weight is None:
                    logger.warning(
                        'Stock adjust: could not parse product from "%s"', name
                    )
                    continue
                try:
                    kb = Kettlebell.objects.select_for_update().filter(
                        weight=weight, weight_unit=unit
                    ).first()
                except Exception:
                    kb = None

            if not kb:
                logger.warning(
                    'Stock adjust: product not found for lineitem %s (order=%s)',
                    getattr(li, 'id', '<unknown>'),
                    order.order_number,
                )
                continue

            try:
                # Decrement but never go negative
                kb.stock = max(0, int(kb.stock) - qty)
                kb.save()
                logger.info(
                    'Stock adjust: decremented %s by %s -> %s (order=%s)',
                    kb.id,
                    qty,
                    kb.stock,
                    order.order_number,
                )
            except Exception:
                logger.exception(
                    'Stock adjust: failed updating stock for order %s lineitem %s',
                    order.order_number,
                    getattr(li, 'id', '<unknown>'),
                )

        # Mark order as adjusted so repeated handlers/webhooks don't
        # decrement stock again. This write is inside the same
        # transaction to keep operations atomic.
        try:
            order.stock_adjusted = True
            order.save(update_fields=['stock_adjusted'])
        except Exception:
            logger.exception(
                'Stock adjust: failed to mark order %s as adjusted',
                order.order_number,
            )


def transfer_basket_to_order(order, request):
    """Copy current basket (DB or session) into the given Order.

    This helper is atomic and will create OrderLineItem rows using
    bulk_create for efficiency. It also computes and persists the
    order.total. The function does not delete the source basket; the
    caller should remove the basket only after payment/fulfillment.
    """
    if order is None or request is None:
        return

    total = Decimal('0.00')
    items_to_create = []

    # Authenticated users: copy from DB BasketItems
    if getattr(request, 'user', None) and request.user.is_authenticated:
        try:
            from basket.models import Basket
            from .models import OrderLineItem

            basket_obj, _ = Basket.objects.get_or_create(user=request.user)
            # Lock the basket to avoid concurrent checkouts
            basket_obj = Basket.objects.select_for_update().get(pk=basket_obj.pk)
            # content_object is a GenericForeignKey and cannot be used with
            # select_related; iterate the items and access content_object
            # lazily. This is slightly less efficient but safe and simple.
            for it in basket_obj.items.select_related('content_type').all():
                qty = int(it.quantity)
                price = Decimal(str(it.price_snapshot))
                # content_object may be None or a related model instance
                content_obj = getattr(it, 'content_object', None)
                name = str(content_obj) if content_obj else str(it)
                items_to_create.append(
                    OrderLineItem(
                        order=order,
                        product=(content_obj if content_obj else None),
                        product_name=name,
                        quantity=qty,
                        price=price,
                    )
                )
                total += price * qty
        except Exception:
            # defensive: if anything goes wrong we bail but keep order empty
            logger.exception(
                'transfer_basket_to_order: failed copying DB basket'
            )

    else:
        # Anonymous/session-based basket
        try:
            from .models import OrderLineItem

            session_basket = request.session.get('basket', {}) or {}
            for weight_str, data in session_basket.items():
                qty = int(data.get('quantity', 0))
                try:
                    price = Decimal(str(data.get('price_gbp', '0')))
                except Exception:
                    price = Decimal('0.00')

                # try to map to a product for a nicer name
                name = f"{weight_str} kg kettlebell"
                kb = None
                try:
                    w = Decimal(str(weight_str))
                    kb = Kettlebell.objects.filter(
                        weight=w,
                        weight_unit='kg',
                    ).first()
                    if kb:
                        name = str(kb)
                except Exception:
                    kb = None

                items_to_create.append(
                    OrderLineItem(
                        order=order,
                        product=kb if kb else None,
                        product_name=name,
                        quantity=qty,
                        price=price,
                    )
                )
                total += price * qty
        except Exception:
            logger.exception(
                'transfer_basket_to_order: failed copying session basket'
            )

    # Persist line items and total inside a transaction
    try:
        with transaction.atomic():
            if items_to_create:
                OrderLineItem.objects.bulk_create(items_to_create)
            order.total = total
            order.save(update_fields=['total'])
    except Exception:
        logger.exception(
            'transfer_basket_to_order: failed creating order line items'
        )
