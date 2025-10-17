from django.urls import path
from . import views

urlpatterns = [
    path('', views.shop_view, name='shop'),
    path('add/', views.add_to_basket, name='add_to_basket'),
]
