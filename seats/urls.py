from django.urls import path
from . import views

urlpatterns = [
    path('', views.seat_list_view, name='seat_list'),
    path('tambah/', views.seat_create_view, name='seat_create'),
    path('<uuid:pk>/edit/', views.seat_update_view, name='seat_update'),
    path('<uuid:pk>/hapus/', views.seat_delete_view, name='seat_delete'),
]
