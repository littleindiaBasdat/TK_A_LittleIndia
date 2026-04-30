from django.urls import path
from . import views

urlpatterns = [
    path('', views.event_list_view, name='event_list'),
    path('saya/', views.my_events_view, name='my_events'),
    path('tambah/', views.event_create_view, name='event_create'),
    path('<uuid:pk>/edit/', views.event_update_view, name='event_update'),
]
