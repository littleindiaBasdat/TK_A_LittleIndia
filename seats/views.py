from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from venues.models import Venue
from .models import Seat


def can_manage(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


@login_required
def seat_list_view(request):
    seats = Seat.objects.select_related('venue').all()
    query = request.GET.get('q', '').strip()
    venue_filter = request.GET.get('venue', '')
    status_filter = request.GET.get('status', '')
    if query:
        seats = seats.filter(Q(section__icontains=query) | Q(row__icontains=query) | Q(number__icontains=query) | Q(venue__name__icontains=query))
    if venue_filter:
        seats = seats.filter(venue_id=venue_filter)
    if status_filter == 'filled':
        seats = seats.filter(ticket__isnull=False)
    elif status_filter == 'available':
        seats = seats.filter(ticket__isnull=True)
    total = seats.count()
    filled = seats.filter(ticket__isnull=False).count()
    available = total - filled
    return render(request, 'seats/seat_list.html', {
        'seats': seats,
        'venues': Venue.objects.all().order_by('name'),
        'query': query,
        'venue_filter': venue_filter,
        'status_filter': status_filter,
        'total': total,
        'filled': filled,
        'available': available,
        'can_manage': can_manage(request.user),
    })


@login_required
def seat_create_view(request):
    if not can_manage(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk menambah kursi.')
        return redirect('seat_list')
    venues = Venue.objects.all().order_by('name')
    if request.method == 'POST':
        venue_id = request.POST.get('venue')
        section = request.POST.get('section', '').strip()
        row = request.POST.get('row', '').strip()
        number = request.POST.get('number', '').strip()
        if not all([venue_id, section, row, number]):
            messages.error(request, 'Semua field wajib diisi.')
        else:
            venue = get_object_or_404(Venue, pk=venue_id)
            if Seat.objects.filter(venue=venue, section=section, row=row, number=number).exists():
                messages.error(request, 'Kursi dengan kombinasi tersebut sudah ada.')
            else:
                Seat.objects.create(venue=venue, section=section, row=row, number=number)
                messages.success(request, 'Kursi berhasil ditambahkan.')
                return redirect('seat_list')
    return render(request, 'seats/seat_form.html', {'venues': venues, 'action': 'create'})


@login_required
def seat_update_view(request, pk):
    if not can_manage(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah kursi.')
        return redirect('seat_list')
    seat = get_object_or_404(Seat, pk=pk)
    venues = Venue.objects.all().order_by('name')
    if request.method == 'POST':
        venue_id = request.POST.get('venue')
        section = request.POST.get('section', '').strip()
        row = request.POST.get('row', '').strip()
        number = request.POST.get('number', '').strip()
        if not all([venue_id, section, row, number]):
            messages.error(request, 'Semua field wajib diisi.')
        else:
            venue = get_object_or_404(Venue, pk=venue_id)
            duplicate = Seat.objects.filter(venue=venue, section=section, row=row, number=number).exclude(pk=seat.pk).exists()
            if duplicate:
                messages.error(request, 'Kursi dengan kombinasi tersebut sudah ada.')
            else:
                seat.venue = venue
                seat.section = section
                seat.row = row
                seat.number = number
                seat.save()
                messages.success(request, 'Kursi berhasil diperbarui.')
                return redirect('seat_list')
    return render(request, 'seats/seat_form.html', {'venues': venues, 'seat': seat, 'action': 'update'})


@login_required
def seat_delete_view(request, pk):
    if not can_manage(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk menghapus kursi.')
        return redirect('seat_list')
    seat = get_object_or_404(Seat, pk=pk)
    if hasattr(seat, 'ticket'):
        messages.error(request, 'Kursi ini sudah di-assign ke tiket dan tidak dapat dihapus. Hapus atau ubah tiket terlebih dahulu.')
        return redirect('seat_list')
    if request.method == 'POST':
        seat.delete()
        messages.success(request, 'Kursi berhasil dihapus.')
        return redirect('seat_list')
    return render(request, 'seats/seat_confirm_delete.html', {'seat': seat})
