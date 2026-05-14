from django.urls import path
from . import views

UUID_PATTERN = '<uuid:pk>'

urlpatterns = [
    path('', views.event_list_view, name='event_list'),
    path('cari/', views.event_browse_view, name='event_browse'),
    path('tambah/', views.event_create_view, name='event_create'),
    path(f'{UUID_PATTERN}/edit/', views.event_update_view, name='event_update'),
]
