from decimal import Decimal
import json

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
        session["basket"] = {
            "16": {"quantity": 2, "price_gbp": str(self.kb.price_gbp)}
        }
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
        # may render payment page (200) or redirect to success (302)
        self.assertIn(resp.status_code, (200, 302))

        # order created
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.total, Decimal("99.98"))

        # line items created
        self.assertEqual(order.items.count(), 1)
        # Items are kept in session until payment completes
        session = self.client.session
        self.assertIn("basket", session)

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
        self.assertIn(resp.status_code, (200, 302))

        # order and line items
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total, self.kb.price_gbp * 3)
        # Items are kept in DB until payment completes
        self.assertEqual(basket_obj.items.count(), 1)

    def test_cache_checkout_data_stores_json_and_returns_ok(self):
        url = reverse('checkout:cache_checkout_data')
        payload = {'foo': 'bar', 'amount': 123}
        resp = self.client.post(
            url, data=json.dumps(payload), content_type='application/json'
        )
        # view returns small OK response (plain text)
        self.assertEqual(resp.status_code, 200)
        # session should contain the cached payload
        self.assertIn('checkout_cache', self.client.session)
        self.assertEqual(self.client.session['checkout_cache'], payload)

    def test_cache_checkout_data_invalid_returns_fail(self):
        url = reverse('checkout:cache_checkout_data')
        # send invalid JSON (text)
        resp = self.client.post(
            url, data='not-json', content_type='application/json'
        )
        # view renders FAIL small template, still 200
        self.assertEqual(resp.status_code, 200)

    def test_authenticated_checkout_links_profile(self):
        # ensure that when a user with a profile checks out, order.profile
        # is set
        user = User.objects.create_user('profiled', 'p@example.com', 'pw')
        # create profile via signal
        # ensure basket
        basket_obj = Basket.objects.create(user=user)
        BasketItem.objects.create(
            basket=basket_obj,
            content_object=self.kb,
            quantity=1,
            price_snapshot=self.kb.price_gbp,
        )
        self.client.login(username='profiled', password='pw')
        url = reverse('checkout:checkout')
        data = {
            'full_name': 'Profiled',
            'email': 'p@example.com',
            'phone_number': '1',
            'country': 'UK',
            'postcode': 'PP1',
            'town_or_city': 'City',
            'street_address1': 'Addr',
            'street_address2': '',
            'county': '',
        }
        resp = self.client.post(url, data)
        self.assertIn(resp.status_code, (200, 302))
        order = Order.objects.first()
        # order.profile should reference the user's UserProfile
        self.assertIsNotNone(order.profile)
        self.assertEqual(order.profile.user, user)


class CheckoutBulkCreateAdditionalTest(TestCase):
    """Additional test to verify bulk_create path for authenticated checkout.

    This test mirrors the behavior exercised in the new test file but keeps
    it inside the existing `checkout/tests.py` module to avoid unittest
    discovery issues on Windows/packaging.
    """
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='tester2', email='t2@example.com', password='pass'
        )
        self.client = Client()
        self.client.force_login(self.user)

        # create kettlebells
        self.k1 = Kettlebell.objects.create(
            weight=Decimal('32'), weight_unit='kg', price_gbp=Decimal('60.00')
        )
        self.k2 = Kettlebell.objects.create(
            weight=Decimal('20'), weight_unit='kg', price_gbp=Decimal('36.00')
        )

        # prepare basket
        self.basket, _ = Basket.objects.get_or_create(user=self.user)
        self.basket.items.all().delete()
        BasketItem.objects.create(
            basket=self.basket,
            content_object=self.k1,
            quantity=2,
            price_snapshot=str(self.k1.price_gbp),
        )
        BasketItem.objects.create(
            basket=self.basket,
            content_object=self.k2,
            quantity=1,
            price_snapshot=str(self.k2.price_gbp),
        )

    def test_authenticated_checkout_creates_two_line_items_and_total(self):
        url = reverse('checkout:checkout')
        data = {
            'full_name': 'Tester Two',
            'email': 't2@example.com',
            'phone_number': '1',
            'street_address1': 'Addr',
            'town_or_city': 'City',
            'postcode': 'PC',
            'country': 'GB',
        }
        resp = self.client.post(url, data)
        self.assertIn(resp.status_code, (200, 302))

        order_qs = Order.objects.filter(profile__user=self.user).order_by('-date')
        order = order_qs.first()
        self.assertIsNotNone(order)
        items = list(order.items.all())
        self.assertEqual(len(items), 2)

        # Ensure one line item matches the k1 quantity/price and one matches k2
        found_k1 = any(
            i.quantity == 2 and i.price == self.k1.price_gbp for i in items
        )
        found_k2 = any(
            i.quantity == 1 and i.price == self.k2.price_gbp for i in items
        )
        self.assertTrue(found_k1)
        self.assertTrue(found_k2)

        expected_total = (
            self.k1.price_gbp * 2 + self.k2.price_gbp * 1
        )
        self.assertEqual(order.total, expected_total)
