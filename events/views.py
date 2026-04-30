from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Event, Artist
from venues.models import Venue
from accounts.models import UserAccount


def event_list_view(request):
    events = Event.objects.select_related('venue', 'organizer').prefetch_related('artists').all()
    query = request.GET.get('q', '')
    venue_filter = request.GET.get('venue', '')
    artist_filter = request.GET.get('artist', '')

    if query:
        events = events.filter(Q(title__icontains=query) | Q(artists__name__icontains=query)).distinct()
    if venue_filter:
        events = events.filter(venue__id=venue_filter)
    if artist_filter:
        events = events.filter(artists__id=artist_filter)

    venues = Venue.objects.all().order_by('name')
    artists = Artist.objects.all().order_by('name')
    return render(request, 'events/event_list.html', {
        'events': events,
        'venues': venues,
        'artists': artists,
        'query': query,
        'venue_filter': venue_filter,
        'artist_filter': artist_filter,
    })


@login_required
def event_create_view(request):
    if request.user.role not in ['admin', 'organizer']:
        messages.error(request, 'Anda tidak memiliki izin untuk membuat event.')
        return redirect('event_list')
    venues = Venue.objects.all().order_by('name')
    artists = Artist.objects.all().order_by('name')
    organizers = UserAccount.objects.filter(role='organizer').order_by('full_name', 'username')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        date = request.POST.get('date', '')
        time = request.POST.get('time', '')
        venue_id = request.POST.get('venue', '')
        description = request.POST.get('description', '').strip()
        artist_ids = request.POST.getlist('artists')
        organizer_id = request.POST.get('organizer', '')
        if request.user.role == 'admin' and not organizer_id:
            messages.error(request, 'Organizer penyelenggara wajib dipilih.')
            return render(request, 'events/event_form.html', {'action': 'create', 'venues': venues, 'artists': artists, 'organizers': organizers})
        if not all([title, date, time, venue_id]):
            messages.error(request, 'Field wajib: Judul, Tanggal, Waktu, dan Venue harus diisi.')
            return render(request, 'events/event_form.html', {'action': 'create', 'venues': venues, 'artists': artists, 'organizers': organizers})
        venue = get_object_or_404(Venue, pk=venue_id)
        organizer = request.user if request.user.role == 'organizer' else get_object_or_404(UserAccount, pk=organizer_id, role='organizer')
        event = Event.objects.create(title=title, date=date, time=time, venue=venue, organizer=organizer, description=description)
        if artist_ids:
            event.artists.set(Artist.objects.filter(id__in=artist_ids))
        if 'image' in request.FILES:
            event.image = request.FILES['image']
            event.save()
        messages.success(request, f'Event "{title}" berhasil dibuat.')
        return redirect('event_list')
    return render(request, 'events/event_form.html', {'action': 'create', 'venues': venues, 'artists': artists, 'organizers': organizers})


@login_required
def event_update_view(request, pk):
    if request.user.role not in ['admin', 'organizer']:
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah event.')
        return redirect('event_list')
    event = get_object_or_404(Event, pk=pk)
    if request.user.role == 'organizer' and event.organizer != request.user:
        messages.error(request, 'Anda hanya dapat mengedit event milik Anda.')
        return redirect('event_list')
    venues = Venue.objects.all().order_by('name')
    artists = Artist.objects.all().order_by('name')
    organizers = UserAccount.objects.filter(role='organizer').order_by('full_name', 'username')
    if request.method == 'POST':
        event.title = request.POST.get('title', event.title).strip()
        event.date = request.POST.get('date', event.date)
        event.time = request.POST.get('time', event.time)
        venue_id = request.POST.get('venue', '')
        if venue_id:
            event.venue = get_object_or_404(Venue, pk=venue_id)
        if request.user.role == 'admin':
            organizer_id = request.POST.get('organizer', '')
            if organizer_id:
                event.organizer = get_object_or_404(UserAccount, pk=organizer_id, role='organizer')
        event.description = request.POST.get('description', event.description)
        artist_ids = request.POST.getlist('artists')
        event.artists.set(Artist.objects.filter(id__in=artist_ids))
        if 'image' in request.FILES:
            event.image = request.FILES['image']
        event.save()
        messages.success(request, f'Event "{event.title}" berhasil diperbarui.')
        return redirect('event_list')
    return render(request, 'events/event_form.html', {'action': 'update', 'event': event, 'venues': venues, 'artists': artists, 'organizers': organizers})


@login_required
def my_events_view(request):
    if request.user.role == 'organizer':
        events = Event.objects.filter(organizer=request.user).select_related('venue').prefetch_related('artists')
    elif request.user.role == 'admin':
        events = Event.objects.all().select_related('venue', 'organizer').prefetch_related('artists')
    else:
        return redirect('event_list')
    return render(request, 'events/my_events.html', {'events': events})
