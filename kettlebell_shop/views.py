
from django.shortcuts import render
from .models import Kettlebell


def shop_view(request):
    kettlebells = Kettlebell.objects.all().order_by('weight')
    return render(
        request,
        'kettlebell_shop/shop.html',
        {'kettlebells': kettlebells}
    )

    def __str__(self):
        return f"{self.weight} kg ({self.stock} in stock)"
