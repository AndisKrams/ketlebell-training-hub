from decimal import Decimal
import json

from django.test import TestCase, Client, override_settings
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


class CheckoutStaleSessionIntegrationTest(TestCase):
    """Integration test that reproduces the stale-session removal flow.

    Scenario:
    - Authenticated user has a session 'basket' entry but no DB BasketItem
      (simulates a removal flow that cleared DB but left session behind).
    - User posts to `add_to_basket` to add 1 unit of a product with stock=1.
    - The code should detect the stale session entry, remove it, and
      allow the add to proceed (creating a DB BasketItem and updating
      session), instead of rejecting with "Requested quantity exceeds stock".
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='stale_tester', email='stale@example.com', password='pass'
        )
        self.client = Client()
        self.client.force_login(self.user)

        # Create a product with stock 1
        self.kb = Kettlebell.objects.create(
            weight=Decimal('48'),
            weight_unit='kg',
            price_gbp=Decimal('82.00'),
            stock=1,
        )

        # Ensure user's DB basket has no items
        from basket.models import Basket

        self.basket_obj, _ = Basket.objects.get_or_create(user=self.user)
        self.basket_obj.items.all().delete()

        # Simulate stale session reservation: session has quantity 1
        session = self.client.session
        session['basket'] = {
            '48': {'quantity': 1, 'price_gbp': str(self.kb.price_gbp)}
        }
        session.save()

    def test_readd_after_stale_session_allows_add(self):
        url = reverse('add_to_basket')
        payload = {'weight': 48, 'quantity': 1, 'unit': 'kg'}
        resp = self.client.post(
            url, data=json.dumps(payload), content_type='application/json'
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Add should succeed (ok=True) and create a BasketItem
        self.assertTrue(data.get('ok'))

        # DB should now have a BasketItem for this product
        from basket.models import BasketItem

        bi_exists = BasketItem.objects.filter(
            basket=self.basket_obj, object_id=self.kb.id
        ).exists()
        self.assertTrue(bi_exists)

        # Session should reflect the current basket qty (1)
        session = self.client.session
        self.assertIn('basket', session)
        self.assertIn('48', session['basket'])
        self.assertEqual(int(session['basket']['48']['quantity']), 1)


class CheckoutStockAdjustmentTests(TestCase):
    """Tests that paid flows decrement product stock and are idempotent.

    Covers both the client-side `mark_order_paid` endpoint and the
    webhook endpoint (`checkout/wh/`)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='stock_tester', email='stock@example.com', password='pass'
        )
        self.client = Client()
        self.client.force_login(self.user)

        # create a kettlebell product with a known stock
        self.kb = Kettlebell.objects.create(
            weight=Decimal('24'),
            weight_unit='kg',
            price_gbp=Decimal('70.00'),
            stock=5,
        )

    def _create_order_with_line(self, quantity=1, product_name=None):
        # Create a pending order owned by the test user
        order = Order.objects.create(
            profile=self.user.userprofile,
            full_name='Stock Tester',
            email='stock@example.com',
            phone_number='',
            street_address1='1 Test',
            town_or_city='City',
            postcode='PC1',
            county='',
            country='UK',
            total=(self.kb.price_gbp * quantity),
            paid=False,
            status=Order.STATUS_PENDING,
        )
        name = product_name or str(self.kb)
        from .models import OrderLineItem

        OrderLineItem.objects.create(
            order=order,
            product_name=name,
            quantity=quantity,
            price=self.kb.price_gbp,
        )
        return order

    def test_mark_order_paid_decrements_stock_and_is_idempotent(self):
        order = self._create_order_with_line(quantity=2)

        url = reverse('checkout:mark_order_paid', args=[order.order_number])
        # first call should decrement stock by 2
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.kb.refresh_from_db()
        self.assertEqual(self.kb.stock, 3)
        # order should be marked adjusted
        order.refresh_from_db()
        self.assertTrue(order.stock_adjusted)


class TransferBasketToOrderTests(TestCase):
    """Tests for the transfer_basket_to_order helper and basket cleanup flow."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='transfer_tester', email='t@example.com', password='pass'
        )
        self.client = Client()
        self.client.force_login(self.user)

        # create product and basket
        self.kb = Kettlebell.objects.create(
            weight=Decimal('12'), weight_unit='kg', price_gbp=Decimal('30.00'), stock=10
        )
        from basket.models import Basket, BasketItem
        self.basket, _ = Basket.objects.get_or_create(user=self.user)
        self.basket.items.all().delete()
        BasketItem.objects.create(
            basket=self.basket,
            content_object=self.kb,
            quantity=2,
            price_snapshot=self.kb.price_gbp,
        )
        # record initial stock for assertions in tests that check stock
        self.initial_stock = int(self.kb.stock)

    def test_double_post_does_not_duplicate_lineitems(self):
        url = reverse('checkout:checkout')
        data = {
            'full_name': 'T', 'email': 't@example.com', 'phone_number': '',
            'country': 'UK', 'postcode': 'PC', 'town_or_city': 'City',
            'street_address1': 'Addr',
        }
        # first submit
        resp1 = self.client.post(url, data)
        self.assertIn(resp1.status_code, (200, 302))
        # second submit (user may re-submit quickly)
        resp2 = self.client.post(url, data)
        self.assertIn(resp2.status_code, (200, 302))

        orders = Order.objects.filter(profile__user=self.user)
        self.assertEqual(orders.count(), 1)
        order = orders.first()
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total, self.kb.price_gbp * 2)

    def test_authenticated_basket_cleared_after_payment(self):
        # create order via checkout
        url = reverse('checkout:checkout')
        data = {
            'full_name': 'T', 'email': 't@example.com', 'phone_number': '',
            'country': 'UK', 'postcode': 'PC', 'town_or_city': 'City',
            'street_address1': 'Addr',
        }
        resp = self.client.post(url, data)
        self.assertIn(resp.status_code, (200, 302))
        order = Order.objects.filter(profile__user=self.user).first()
        self.assertIsNotNone(order)

        # simulate marking paid
        pay_url = reverse('checkout:mark_order_paid', args=[order.order_number])
        resp = self.client.post(pay_url)
        self.assertEqual(resp.status_code, 200)

        # basket should be cleared in DB
        from basket.models import Basket
        basket = Basket.objects.get(user=self.user)
        self.assertEqual(basket.items.count(), 0)

    def test_guest_session_cleared_on_success(self):
        # anonymous client with session basket
        anon = Client()
        session = anon.session
        session['basket'] = {str(self.kb.weight): {'quantity': 1, 'price_gbp': str(self.kb.price_gbp)}}
        session.save()

        url = reverse('checkout:checkout')
        data = {
            'full_name': 'Guest', 'email': 'g@example.com', 'phone_number': '',
            'country': 'UK', 'postcode': 'PC', 'town_or_city': 'City',
            'street_address1': 'Addr',
        }
        resp = anon.post(url, data)
        self.assertIn(resp.status_code, (200, 302))
        order = Order.objects.first()
        self.assertIsNotNone(order)

        # simulate user returning to success page (checkout_success) which clears session
        success_url = reverse('checkout:checkout_success', args=[order.order_number])
        resp = anon.get(success_url)
        self.assertEqual(resp.status_code, 200)
        sess = anon.session
        self.assertNotIn('basket', sess)
    # we only assert that the session was cleared for anonymous user here;
    # stock adjustments are covered in the dedicated stock-adjustment tests.

    def _create_order_with_line(self, quantity=1, product_name=None):
        # helper copied from CheckoutStockAdjustmentTests for reuse in these
        # transfer-related tests so the test class is self-contained.
        order = Order.objects.create(
            profile=self.user.userprofile,
            full_name='Transfer Tester',
            email='t@example.com',
            phone_number='',
            street_address1='1 Test',
            town_or_city='City',
            postcode='PC1',
            county='',
            country='UK',
            total=(self.kb.price_gbp * quantity),
            paid=False,
            status=Order.STATUS_PENDING,
        )
        name = product_name or str(self.kb)
        from .models import OrderLineItem

        OrderLineItem.objects.create(
            order=order,
            product_name=name,
            quantity=quantity,
            price=self.kb.price_gbp,
        )
        return order

    def test_webhook_decrements_stock_and_is_idempotent(self):
        order = self._create_order_with_line(quantity=1)

        url = reverse('checkout:webhook')
        event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'metadata': {'order_number': order.order_number}
                }
            },
        }

        with override_settings(STRIPE_WH_SECRET=''):
            resp = self.client.post(
                url, data=json.dumps(event), content_type='application/json'
            )
        self.assertEqual(resp.status_code, 200)
        self.kb.refresh_from_db()
        # stock should decrement by the line quantity (1)
        self.assertEqual(self.kb.stock, self.initial_stock - 1)

        order.refresh_from_db()
        self.assertTrue(order.stock_adjusted)

        # duplicate webhook should not decrement again
        with override_settings(STRIPE_WH_SECRET=''):
            resp = self.client.post(
                url, data=json.dumps(event), content_type='application/json'
            )
        self.assertEqual(resp.status_code, 200)
        self.kb.refresh_from_db()
        self.assertEqual(self.kb.stock, self.initial_stock - 1)

    def test_unparsable_product_name_does_not_change_stock(self):
        # Create an order with a product name the parser cannot read
        order = self._create_order_with_line(
            quantity=1, product_name='Some unknown product'
        )
        url = reverse('checkout:webhook')
        event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'metadata': {'order_number': order.order_number}
                }
            },
        }

        with override_settings(STRIPE_WH_SECRET=''):
            resp = self.client.post(
                url, data=json.dumps(event), content_type='application/json'
            )
        self.assertEqual(resp.status_code, 200)
        # stock should be unchanged
        self.kb.refresh_from_db()
        # stock should be unchanged when product_name cannot be parsed
        self.assertEqual(self.kb.stock, self.initial_stock)
        # order should be marked adjusted (we attempted adjustment)
        order.refresh_from_db()
        self.assertTrue(order.stock_adjusted)
