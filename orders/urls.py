from django.urls import path
from . import views

urlpatterns = [
    path('', views.order_list_view, name='order_list'),
    path('tambah/', views.order_create_view, name='order_create'),
    path('<uuid:pk>/edit/', views.order_update_view, name='order_update'),
    path('<uuid:pk>/hapus/', views.order_delete_view, name='order_delete'),
]
