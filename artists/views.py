from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from events.models import Artist


def artist_list_view(request):
    artists = Artist.objects.all().order_by('name')
    query = request.GET.get('q', '').strip()
    genre_filter = request.GET.get('genre', '').strip()
    if query:
        artists = artists.filter(name__icontains=query)
    if genre_filter:
        artists = artists.filter(genre__iexact=genre_filter)
    genres = Artist.objects.exclude(genre='').values_list('genre', flat=True).distinct().order_by('genre')
    return render(request, 'artists/artist_list.html', {
        'artists': artists,
        'genres': genres,
        'query': query,
        'genre_filter': genre_filter,
        'can_admin': request.user.is_authenticated and request.user.role == 'admin',
    })


def artist_create_view(request):
    if not request.user.is_authenticated or request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat membuat artist.')
        return redirect('artist_list')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        genre = request.POST.get('genre', '').strip()
        if not name:
            messages.error(request, 'Name wajib diisi.')
        else:
            Artist.objects.create(name=name, genre=genre)
            messages.success(request, 'Artist berhasil dibuat.')
            return redirect('artist_list')
    return render(request, 'artists/artist_form.html', {'action': 'create'})


def artist_update_view(request, pk):
    if not request.user.is_authenticated or request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat mengubah artist.')
        return redirect('artist_list')
    artist = get_object_or_404(Artist, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        genre = request.POST.get('genre', '').strip()
        if not name:
            messages.error(request, 'Name wajib diisi.')
        else:
            artist.name = name
            artist.genre = genre
            artist.save()
            messages.success(request, 'Artist berhasil diperbarui.')
            return redirect('artist_list')
    return render(request, 'artists/artist_form.html', {'artist': artist, 'action': 'update'})


def artist_delete_view(request, pk):
    if not request.user.is_authenticated or request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat menghapus artist.')
        return redirect('artist_list')
    artist = get_object_or_404(Artist, pk=pk)
    if request.method == 'POST':
        artist.delete()
        messages.success(request, 'Artist berhasil dihapus.')
        return redirect('artist_list')
    return render(request, 'artists/artist_confirm_delete.html', {'artist': artist})
