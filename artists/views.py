from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import connection
from events.models import Artist


def artist_list_view(request):
    query = request.GET.get('q', '').strip()
    genre_filter = request.GET.get('genre', '').strip()
    
    # Build SQL query untuk artists
    sql = "SELECT * FROM artist WHERE 1=1"
    params = []
    
    if query:
        sql += " AND name ILIKE %s"
        params.append(f"%{query}%")
    
    if genre_filter:
        sql += " AND genre ILIKE %s"
        params.append(f"%{genre_filter}%")
    
    sql += " ORDER BY name"
    
    # Fetch artists dengan parameter binding
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        artists = [dict(zip(cols, row)) for row in cursor.fetchall()]
    
    # Fetch distinct genres
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT genre FROM artist WHERE genre != '' ORDER BY genre"
        )
        genres = [row[0] for row in cursor.fetchall()]
    
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
