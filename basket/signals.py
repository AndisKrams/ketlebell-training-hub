from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import Basket, BasketItem


@receiver(user_logged_in)
def merge_session_basket(sender, user, request, **kwargs):
    """Merge session basket into user's DB basket on login."""
    session_basket = request.session.get('basket')
    if not session_basket:
        return

    basket_obj, _ = Basket.objects.get_or_create(user=user)

    for weight_str, item in session_basket.items():
        try:
            # kettlebell product is identified by weight field; find the object
            from kettlebell_shop.models import Kettlebell
            weight = int(weight_str)
            product = Kettlebell.objects.filter(weight=weight).first()
            if not product:
                continue
            ct = ContentType.objects.get_for_model(product)
            qty = int(item.get('quantity', 0))
            if qty <= 0:
                continue
            bi, created = BasketItem.objects.get_or_create(
                basket=basket_obj,
                content_type=ct,
                object_id=product.id,
                defaults={
                    'quantity': qty,
                    'price_snapshot': product.price_gbp,
                },
            )
            if not created:
                bi.quantity = bi.quantity + qty
                bi.price_snapshot = product.price_gbp
                bi.save()
        except Exception:
            continue

    # Optionally clear session basket after merging
    try:
        del request.session['basket']
        request.session.modified = True
    except KeyError:
        pass
    request.session['basket_merged'] = True


try:
    from allauth.account.signals import user_signed_up

    # connect the same handler to signup
    user_signed_up.connect(merge_session_basket)
except Exception:
    # allauth not installed or import failed; ignore
    pass
