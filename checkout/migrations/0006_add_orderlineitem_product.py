"""Add product FK to OrderLineItem and populate existing rows where possible.

This migration adds a nullable ForeignKey to `kettlebell_shop.Kettlebell` on
`OrderLineItem` and attempts a best-effort population of existing rows by
parsing the `product_name` for a weight and unit and matching a Kettlebell.
"""
from __future__ import unicode_literals

from decimal import Decimal, InvalidOperation
import re

from django.db import migrations, models


def _parse_weight_unit(name):
    # best-effort: look for a leading number and optional unit (kg|lb)
    if not name:
        return None, None
    m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|lb)?", name, re.I)
    if not m:
        return None, None
    try:
        w = Decimal(m.group(1))
    except (InvalidOperation, TypeError):
        return None, None
    unit = (m.group(2) or 'kg').lower()
    if unit not in ('kg', 'lb'):
        unit = 'kg'
    return w, unit


def populate_product(apps, schema_editor):
    OrderLineItem = apps.get_model('checkout', 'OrderLineItem')
    Kettlebell = apps.get_model('kettlebell_shop', 'Kettlebell')

    for oli in OrderLineItem.objects.all():
        name = (oli.product_name or '').strip()
        weight, unit = _parse_weight_unit(name)
        if weight is None:
            continue
        kb = Kettlebell.objects.filter(weight=weight, weight_unit=unit).first()
        if kb:
            oli.product_id = kb.pk
            oli.save(update_fields=['product_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('checkout', '0005_add_stock_adjusted'),
        ('kettlebell_shop', '0006_remove_kettlebell_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderlineitem',
            name='product',
            field=models.ForeignKey(
                to='kettlebell_shop.Kettlebell',
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
                related_name='order_line_items',
            ),
        ),
        migrations.RunPython(
            populate_product, reverse_code=migrations.RunPython.noop
        ),
    ]
