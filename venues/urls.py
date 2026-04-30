from django.urls import path
from . import views

urlpatterns = [
    path('', views.venue_list_view, name='venue_list'),
    path('tambah/', views.venue_create_view, name='venue_create'),
    path('<uuid:pk>/edit/', views.venue_update_view, name='venue_update'),
    path('<uuid:pk>/hapus/', views.venue_delete_view, name='venue_delete'),
]
