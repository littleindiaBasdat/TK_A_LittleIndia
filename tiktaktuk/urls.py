from django.shortcuts import redirect
from django.urls import include, path
from tickets import views as ticket_views

urlpatterns = [
    path('', lambda request: redirect('dashboard' if request.user.is_authenticated else 'login')),
    path('my-tickets/', ticket_views.ticket_list_view, name='my_tickets'),
    path('', include('accounts.urls')),
    path('artists/', include('artists.urls')),
    path('events/', include('events.urls')),
    path('orders/', include('orders.urls')),
    path('promotions/', include('promotions.urls')),
    path('seats/', include('seats.urls')),
    path('tickets/', include('tickets.urls')),
    path('venues/', include('venues.urls')),
]
