from django.urls import path
from . import views
from .webhooks import webhook

urlpatterns = [
     path('', views.checkout, name='checkout'),
     path(
          'checkout_success/<order_number>/',
          views.checkout_success,
          name='checkout_success',
     ),
     path(
          'cache_checkout_data/',
          views.cache_checkout_data,
          name='cache_checkout_data',
     ),
     path('wh/', webhook, name='webhook'),
     path(
          'create-session/<order_number>/',
          views.create_checkout_session,
          name='create_session',
     ),
     path(
          'create-payment-intent/<order_number>/',
          views.create_payment_intent,
          name='create_payment_intent',
     ),
]
