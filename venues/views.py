from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Venue


def venue_list_view(request):
    venues = Venue.objects.all()
    query = request.GET.get('q', '')
    city_filter = request.GET.get('city', '')
    seating_filter = request.GET.get('seating', '')

    if query:
        venues = venues.filter(Q(name__icontains=query) | Q(address__icontains=query))
    if city_filter:
        venues = venues.filter(city__icontains=city_filter)
    if seating_filter:
        venues = venues.filter(seating_type=seating_filter)

    cities = Venue.objects.values_list('city', flat=True).distinct().order_by('city')
    return render(request, 'venues/venue_list.html', {
        'venues': venues,
        'cities': cities,
        'query': query,
        'city_filter': city_filter,
        'seating_filter': seating_filter,
    })


@login_required
def venue_create_view(request):
    if request.user.role not in ['admin', 'organizer']:
        messages.error(request, 'Anda tidak memiliki izin untuk menambah venue.')
        return redirect('venue_list')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        capacity = request.POST.get('capacity', '0')
        seating_type = request.POST.get('seating_type', 'free')
        if not all([name, address, city, capacity]):
            messages.error(request, 'Semua field wajib diisi.')
        elif not capacity.isdigit() or int(capacity) < 1:
            messages.error(request, 'Kapasitas harus berupa bilangan positif.')
        else:
            Venue.objects.create(name=name, address=address, city=city, capacity=int(capacity), seating_type=seating_type)
            messages.success(request, f'Venue "{name}" berhasil ditambahkan.')
            return redirect('venue_list')
    return render(request, 'venues/venue_form.html', {'action': 'create'})


@login_required
def venue_update_view(request, pk):
    if request.user.role not in ['admin', 'organizer']:
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah venue.')
        return redirect('venue_list')
    venue = get_object_or_404(Venue, pk=pk)
    if request.method == 'POST':
        capacity = request.POST.get('capacity', str(venue.capacity))
        if not capacity.isdigit() or int(capacity) < 1:
            messages.error(request, 'Kapasitas harus berupa bilangan positif.')
        else:
            venue.name = request.POST.get('name', venue.name).strip()
            venue.address = request.POST.get('address', venue.address).strip()
            venue.city = request.POST.get('city', venue.city).strip()
            venue.capacity = int(capacity)
            venue.seating_type = request.POST.get('seating_type', venue.seating_type)
            venue.save()
            messages.success(request, f'Venue "{venue.name}" berhasil diperbarui.')
            return redirect('venue_list')
    return render(request, 'venues/venue_form.html', {'action': 'update', 'venue': venue})


@login_required
def venue_delete_view(request, pk):
    if request.user.role not in ['admin', 'organizer']:
        messages.error(request, 'Anda tidak memiliki izin untuk menghapus venue.')
        return redirect('venue_list')
    venue = get_object_or_404(Venue, pk=pk)
    if request.method == 'POST':
        name = venue.name
        venue.delete()
        messages.success(request, f'Venue "{name}" berhasil dihapus.')
        return redirect('venue_list')
    return render(request, 'venues/venue_confirm_delete.html', {'venue': venue})
