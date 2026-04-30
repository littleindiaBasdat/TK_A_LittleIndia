from django.urls import path
from . import views

urlpatterns = [
    path('', views.ticket_list_view, name='ticket_list'),
    path('kategori/', views.ticket_category_list_view, name='ticket_category_list'),
    path('kategori/tambah/', views.ticket_category_create_view, name='ticket_category_create'),
    path('kategori/<uuid:pk>/edit/', views.ticket_category_update_view, name='ticket_category_update'),
    path('kategori/<uuid:pk>/hapus/', views.ticket_category_delete_view, name='ticket_category_delete'),
    path('tambah/', views.ticket_create_view, name='ticket_create'),
    path('<uuid:pk>/edit/', views.ticket_update_view, name='ticket_update'),
    path('<uuid:pk>/hapus/', views.ticket_delete_view, name='ticket_delete'),
]
