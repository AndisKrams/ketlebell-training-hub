from django.urls import path
from . import views

app_name = 'basket'

urlpatterns = [
    path('', views.view_basket, name='view'),
    path('update/<int:item_id>/', views.update_item, name='update'),
    path('api/', views.basket_api, name='api'),
    path(
        'api/clear-merge-flag/',
        views.clear_merge_flag,
        name='clear_merge_flag',
    ),
    path('api/contents/', views.basket_contents_api, name='api_contents'),
    path('api/clear/', views.clear_basket_api, name='api_clear'),
    path('api/update/', views.basket_update_api, name='api_update'),
]
