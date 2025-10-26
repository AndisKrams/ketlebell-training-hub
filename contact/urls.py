from django.urls import path
from . import views

app_name = 'contact'

urlpatterns = [
    path('order/<order_number>/', views.contact_order, name='contact_order'),
    path('success/', views.contact_success, name='contact_success'),
]
