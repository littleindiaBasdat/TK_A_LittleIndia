from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path('', lambda request: redirect('dashboard' if request.user.is_authenticated else 'login')),
    path('', include('accounts.urls')),
    path('artists/', include('artists.urls')),
    path('events/', include('events.urls')),
    path('orders/', include('orders.urls')),
    path('promotions/', include('promotions.urls')),
    path('seats/', include('seats.urls')),
    path('tickets/', include('tickets.urls')),
    path('venues/', include('venues.urls')),
]
