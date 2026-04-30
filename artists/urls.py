from django.urls import path
from . import views

urlpatterns = [
    path('', views.artist_list_view, name='artist_list'),
    path('tambah/', views.artist_create_view, name='artist_create'),
    path('<uuid:pk>/edit/', views.artist_update_view, name='artist_update'),
    path('<uuid:pk>/hapus/', views.artist_delete_view, name='artist_delete'),
]
