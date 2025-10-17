from django.urls import path
from . import views

app_name = 'basket'

urlpatterns = [
    path('', views.view_basket, name='view'),
    path('update/<int:item_id>/', views.update_item, name='update'),
    path('api/', views.basket_api, name='api'),
    path(
        'api/clear-merge-flag/', views.clear_merge_flag, name='clear_merge_flag'
    ),
]
