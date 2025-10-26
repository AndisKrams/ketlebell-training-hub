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
     path('resume/<order_number>/', views.resume_checkout, name='resume'),
     path('order/<order_number>/', views.order_detail, name='order_detail'),
     path(
          'mark-paid/<order_number>/',
          views.mark_order_paid,
          name='mark_order_paid',
     ),
     path(
          'cancel-order/<order_number>/',
          views.cancel_order,
          name='cancel_order',
     ),
]
