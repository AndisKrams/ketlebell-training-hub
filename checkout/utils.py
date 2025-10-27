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

    with transaction.atomic():
        for li in order.items.select_related():
            name = (li.product_name or '').strip()
            weight, unit = _parse_weight_unit_from_name(name)
            if weight is None:
                logger.warning('Stock adjust: could not parse product from "%s"', name)
                continue

            try:
                kb = Kettlebell.objects.select_for_update().filter(
                    weight=weight, weight_unit=unit
                ).first()
                if not kb:
                    logger.warning('Stock adjust: product not found for %s %s', weight, unit)
                    continue

                qty = int(li.quantity or 0)
                if qty <= 0:
                    continue

                before = kb.stock
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
                logger.exception('Stock adjust: failed for order %s lineitem %s', order.order_number, li.id)
