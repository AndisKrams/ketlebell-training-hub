from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from kettlebell_shop.models import Kettlebell
from basket.models import Basket, BasketItem
from .models import Order


class CheckoutTests(TestCase):
    def setUp(self):
        # create a product
        self.kb = Kettlebell.objects.create(
            weight=Decimal("16.0"),
            weight_unit="kg",
            preset_weight=None,
            price_gbp=Decimal("49.99"),
            stock=10,
        )
        self.client = Client()

    def test_anonymous_checkout_creates_order_and_clears_session(self):
        # prepare session basket
        session = self.client.session
        session["basket"] = {"16": {"quantity": 2, "price_gbp": str(self.kb.price_gbp)}}
        session.save()

        url = reverse("checkout:checkout")
        data = {
            "full_name": "Test User",
            "email": "anon@example.com",
            "phone_number": "12345",
            "country": "UK",
            "postcode": "AB12",
            "town_or_city": "Town",
            "street_address1": "1 Road",
            "street_address2": "",
            "county": "County",
        }
        resp = self.client.post(url, data)
        # should redirect to success
        self.assertEqual(resp.status_code, 302)

        # order created
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.total, Decimal("99.98"))

        # line items created
        self.assertEqual(order.items.count(), 1)

        # session cleared
        session = self.client.session
        self.assertNotIn("basket", session)

    def test_authenticated_checkout_copies_basketitems_and_clears_db(self):
        user = User.objects.create_user("buyer", "b@example.com", "pass")
        basket_obj = Basket.objects.create(user=user)
        # add a BasketItem
        BasketItem.objects.create(
            basket=basket_obj,
            content_object=self.kb,
            quantity=3,
            price_snapshot=self.kb.price_gbp,
        )

        self.client.login(username="buyer", password="pass")

        url = reverse("checkout:checkout")
        data = {
            "full_name": "Buyer Name",
            "email": "b@example.com",
            "phone_number": "555",
            "country": "UK",
            "postcode": "XY99",
            "town_or_city": "City",
            "street_address1": "2 Road",
            "street_address2": "",
            "county": "County",
        }
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)

        # order and line items
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total, self.kb.price_gbp * 3)

        # DB basket cleared
        self.assertEqual(basket_obj.items.count(), 0)
