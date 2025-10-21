from django.contrib import admin
from .models import Kettlebell


@admin.register(Kettlebell)
class KettlebellAdmin(admin.ModelAdmin):
    list_display = (
        'weight', 'weight_unit', 'preset_weight', 'price_gbp', 'stock'
    )
    list_filter = ('weight_unit',)
    search_fields = ('weight',)
    fields = (
        'preset_weight', 'weight', 'weight_unit', 'price_gbp', 'stock'
    )
