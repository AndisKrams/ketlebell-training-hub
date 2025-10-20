from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType

from .models import Basket, BasketItem
from kettlebell_shop.models import Kettlebell


class ClearBasketAPITest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_clear_basket_anonymous(self):
        # Put something in the session basket
        session = self.client.session
        session["basket"] = {"16": {"quantity": 2, "price_gbp": "20.00"}}
        session.save()

        resp = self.client.post(reverse("basket:api_clear"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("count", data)
        self.assertEqual(data["count"], 0)
        # session basket should be removed or empty
        session = self.client.session
        self.assertFalse(session.get("basket"))

    def test_clear_basket_authenticated(self):
        User = get_user_model()
        user = User.objects.create_user(username="tester", password="secret")
        # create a kettlebell product to reference
        kb = Kettlebell.objects.create(weight=16, price_gbp="20.00", stock=10)

        # create basket and item
        basket = Basket.objects.create(user=user)
        ct = ContentType.objects.get_for_model(Kettlebell)
        BasketItem.objects.create(
            basket=basket,
            content_type=ct,
            object_id=kb.id,
            quantity=2,
            price_snapshot="20.00",
        )

        self.client.login(username="tester", password="secret")
        resp = self.client.post(reverse("basket:api_clear"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("count", data)
        self.assertEqual(data["count"], 0)
        # ensure DB items deleted
        self.assertEqual(basket.items.count(), 0)
