from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User

from .models import UserProfile
from .forms import UserProfileForm
from .views import _get_saved_payment_methods


class UserProfileFormTests(TestCase):
	def test_full_name_and_email_saved_to_user(self):
		user = User.objects.create_user(username='alice', password='pass')
		profile, _ = UserProfile.objects.get_or_create(user=user)

		data = {
			'full_name': 'Alice Wonderland',
			'email': 'alice@example.com',
			# include some profile fields so form is valid
			'default_phone_number': '0123456789',
			'default_postcode': 'AB12 3CD',
			'default_town_or_city': 'Town',
			'default_street_address1': '1 Road',
			'default_street_address2': '',
			'default_county': '',
			'default_country': '',
		}

		form = UserProfileForm(data, instance=profile)
		self.assertTrue(form.is_valid(), form.errors.as_json())
		form.save()

		user.refresh_from_db()
		self.assertEqual(user.first_name, 'Alice')
		self.assertEqual(user.last_name, 'Wonderland')
		self.assertEqual(user.email, 'alice@example.com')


class SavedPaymentMethodsTests(TestCase):
	@patch('stripe.Customer.retrieve')
	@patch('stripe.PaymentMethod.list')
	def test_get_saved_payment_methods_includes_default_flag(self, mock_pm_list, mock_cust_retrieve):
		# Prepare a fake profile with a stripe_customer_id
		user = User.objects.create_user(username='bob', password='pass')
		profile, _ = UserProfile.objects.get_or_create(user=user)
		profile.stripe_customer_id = 'cus_123'
		profile.save()

		# Mock payment methods list
		mock_pm_list.return_value = {
			'data': [
				{
					'id': 'pm_1',
					'card': {
						'brand': 'visa',
						'last4': '4242',
						'exp_month': 12,
						'exp_year': 2030,
					},
				}
			]
		}

		# Mock customer retrieve to indicate default payment method
		mock_cust_retrieve.return_value = {
			'invoice_settings': {'default_payment_method': 'pm_1'}
		}

		methods = _get_saved_payment_methods(profile)
		self.assertEqual(len(methods), 1)
		pm = methods[0]
		self.assertEqual(pm['id'], 'pm_1')
		self.assertEqual(pm['brand'], 'visa')
		self.assertEqual(pm['last4'], '4242')
		self.assertTrue(pm.get('is_default'))
