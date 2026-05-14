from django.urls import path
from . import views

UUID_PATTERN = '<uuid:pk>'

urlpatterns = [
    path('', views.venue_list_view, name='venue_list'),
    path('tambah/', views.venue_create_view, name='venue_create'),
    path(f'{UUID_PATTERN}/edit/', views.venue_update_view, name='venue_update'),
    path(f'{UUID_PATTERN}/hapus/', views.venue_delete_view, name='venue_delete'),
]
