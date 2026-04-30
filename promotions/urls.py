from django.urls import path
from . import views

urlpatterns = [
    path('', views.promotion_list_view, name='promotion_list'),
    path('tambah/', views.promotion_create_view, name='promotion_create'),
    path('<uuid:pk>/edit/', views.promotion_update_view, name='promotion_update'),
    path('<uuid:pk>/hapus/', views.promotion_delete_view, name='promotion_delete'),
]
