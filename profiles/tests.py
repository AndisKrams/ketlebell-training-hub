from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User

from .models import UserProfile
from .forms import UserProfileForm
from .views import _get_saved_payment_methods


class UserProfileFormTests(TestCase):
    def test_full_name_and_email_saved_to_user(self):
        user = User.objects.create_user(username="alice", password="pass")
        profile, _ = UserProfile.objects.get_or_create(user=user)

        data = {
            "full_name": "Alice Wonderland",
            "email": "alice@example.com",
            # include some profile fields so form is valid
            "default_phone_number": "0123456789",
            "default_postcode": "AB12 3CD",
            "default_town_or_city": "Town",
            "default_street_address1": "1 Road",
            "default_street_address2": "",
            "default_county": "",
            "default_country": "",
        }

        form = UserProfileForm(data, instance=profile)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        user.refresh_from_db()
        self.assertEqual(user.first_name, "Alice")
        self.assertEqual(user.last_name, "Wonderland")
        self.assertEqual(user.email, "alice@example.com")


class SavedPaymentMethodsTests(TestCase):
    @patch("stripe.Customer.retrieve")
    @patch("stripe.PaymentMethod.list")
    def test_get_saved_payment_methods_includes_default_flag(
        self, mock_pm_list, mock_cust_retrieve
    ):
        # Prepare a fake profile with a stripe_customer_id
        user = User.objects.create_user(username="bob", password="pass")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.stripe_customer_id = "cus_123"
        profile.save()

        # Mock payment methods list
        mock_pm_list.return_value = {
            "data": [
                {
                    "id": "pm_1",
                    "card": {
                        "brand": "visa",
                        "last4": "4242",
                        "exp_month": 12,
                        "exp_year": 2030,
                    },
                }
            ]
        }

        # Mock customer retrieve to indicate default payment method
        mock_cust_retrieve.return_value = {
            "invoice_settings": {"default_payment_method": "pm_1"}
        }

        methods = _get_saved_payment_methods(profile)
        self.assertEqual(len(methods), 1)
        pm = methods[0]
        self.assertEqual(pm["id"], "pm_1")
        self.assertEqual(pm["brand"], "visa")
        self.assertEqual(pm["last4"], "4242")
        self.assertTrue(pm.get("is_default"))

    from decimal import Decimal
    from django.test import Client
    from django.urls import reverse
    from checkout.models import Order, OrderLineItem
    from kettlebell_shop.models import Kettlebell

    class ProfileQueryCountTest(TestCase):
        def setUp(self):
            self.user = User.objects.create_user(
                username="qcuser", email="qc@example.com", password="pw"
            )
            self.client = Client()
            self.client.force_login(self.user)

            # create a kettlebell product for line items
            self.kb = Kettlebell.objects.create(
                weight=Decimal("16.00"),
                weight_unit="kg",
                price_gbp=Decimal("49.99"),
            )

            # create multiple orders with items for this user
            for i in range(3):
                o = Order.objects.create(
                    full_name="QC User",
                    email="qc@example.com",
                    total=Decimal("0.00"),
                    status=Order.STATUS_PENDING,
                )
                # attach to user profile if present
                try:
                    up = self.user.userprofile
                    o.profile = up
                    o.save()
                except Exception:
                    pass
                # add two line items
                OrderLineItem.objects.create(
                    order=o,
                    product_name=str(self.kb),
                    quantity=1,
                    price=self.kb.price_gbp,
                )
                OrderLineItem.objects.create(
                    order=o,
                    product_name=str(self.kb),
                    quantity=2,
                    price=self.kb.price_gbp,
                )
                # recompute total
                o.total = self.kb.price_gbp * 3
                o.save()

        def test_profile_page_query_count(self):
            url = reverse("profiles:profile")
            # We expect the view to fetch profile, orders and prefetch items.
            # Allow up to 6 queries as a conservative bound (platform differences).
            with self.assertNumQueries(6):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                # basic sanity: orders present in context
                self.assertIn("orders", resp.context)
                self.assertGreaterEqual(len(list(resp.context["orders"])), 3)
