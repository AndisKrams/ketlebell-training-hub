from django.urls import path
from . import views

app_name = 'profiles'

urlpatterns = [
    path('', views.profile_view, name='profile'),
    path(
        'remove-payment-method/<str:pm_id>/',
        views.remove_payment_method,
        name='remove_payment_method',
    ),
]
