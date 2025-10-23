from django.db import models
from decimal import Decimal


class Kettlebell(models.Model):
    """Kettlebell product.

    weight: numeric weight value. Stored in the unit specified by
    `weight_unit`.
    weight_unit: 'kg' or 'lb'.
    """
    # Preserve the original presets as choices for admin convenience
    WEIGHT_CHOICES = [
        ("8", "8 kg"),
        ("12", "12 kg"),
        ("16", "16 kg"),
        ("20", "20 kg"),
        ("24", "24 kg"),
        ("28", "28 kg"),
        ("32", "32 kg"),
        ("36", "36 kg"),
        ("40", "40 kg"),
        ("48", "48 kg"),
    ]

    WEIGHT_UNIT_CHOICES = [('kg', 'kg'), ('lb', 'lb')]

    # Keep a small precision for weights (e.g. 16.00)
    weight = models.DecimalField(max_digits=6, decimal_places=2)
    # optional preset selector: when set, the model will copy this value into
    # `weight` on save. Leave blank to enter a custom weight manually.
    preset_weight = models.CharField(
        max_length=10, choices=WEIGHT_CHOICES, blank=True, null=True,
        help_text="Pick a preset kg weight or leave blank for a custom weight",
    )
    weight_unit = models.CharField(
        max_length=2, choices=WEIGHT_UNIT_CHOICES, default='kg'
    )
    stock = models.PositiveIntegerField(default=0)
    price_gbp = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Price in GBP",
    )

    class Meta:
        # allow multiple kettlebells with same numeric weight if unit differs
        unique_together = (('weight', 'weight_unit'),)

    def __str__(self):
        # Do not include stock availability in the display string; the
        # checkout/order summary should not expose live stock counts.
        return f"{self.weight} {self.weight_unit} (£{self.price_gbp})"

    def save(self, *args, **kwargs):
        # If a preset was selected, use it to set the numeric weight and unit
        from decimal import Decimal

        if self.preset_weight:
            try:
                self.weight = Decimal(self.preset_weight)
                # presets are kg
                self.weight_unit = 'kg'
            except Exception:
                # fall back to whatever weight is already set
                pass
        super().save(*args, **kwargs)
