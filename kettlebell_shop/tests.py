from django.test import TestCase
from django.urls import reverse, resolve


class URLResolutionTests(TestCase):
	def test_named_urls_reverse_and_resolve(self):
		cases = [
			("shop", {}),
			("add_to_basket", {}),
			("basket:view", {}),
			("basket:api_contents", {}),
			("basket:api_update", {}),
			("basket:api_clear", {}),
			("basket:clear_merge_flag", {}),
			("checkout:checkout", {}),
			("checkout:order_detail", {"order_number": "ORD123"}),
			("checkout:cancel_order", {"order_number": "ORD123"}),
			("checkout:resume", {"order_number": "ORD123"}),
			("checkout:checkout_success", {"order_number": "ORD123"}),
			("checkout:create_payment_intent", {"order_number": "ORD123"}),
			("checkout:mark_order_paid", {"order_number": "ORD123"}),
			("profiles:profile", {}),
			("profiles:remove_payment_method", {"pm_id": "pm_123"}),
			("contact:contact_order", {"order_number": "ORD123"}),
			("contact:contact_success", {}),
			("about:about", {}),
			("account_login", {}),
			("account_logout", {}),
			("account_signup", {}),
			("account_reset_password", {}),
			("admin:index", {}),
		]

		for name, kwargs in cases:
			url = reverse(name, kwargs=kwargs or None)
			match = resolve(url)
			self.assertIsNotNone(match)
			self.assertIsNotNone(match.func)

	def test_absolute_paths_resolve(self):
		self.assertEqual(reverse("shop"), "/")
		self.assertEqual(reverse("checkout:checkout"), "/checkout/")
		m1 = resolve("/")
		self.assertEqual(m1.url_name, "shop")
		m2 = resolve("/checkout/")
		self.assertEqual(m2.url_name, "checkout")
		m3 = resolve("/profiles/")
		self.assertEqual(m3.url_name, "profile")
