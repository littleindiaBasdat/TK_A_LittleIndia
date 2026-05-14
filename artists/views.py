from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import connection
from accounts.middleware import raw_sql_login_required
import uuid


@raw_sql_login_required
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


@raw_sql_login_required
def artist_create_view(request):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat membuat artist.')
        return redirect('artist_list')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        genre = request.POST.get('genre', '').strip()
        
        if not name:
            messages.error(request, 'Nama artist wajib diisi.')
            return render(request, 'artists/artist_form.html', {'action': 'create'})
        
        artist_id = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO artist (artist_id, name, genre) VALUES (%s, %s, %s)",
                [artist_id, name, genre or None]
            )
        
        messages.success(request, 'Artist berhasil dibuat.')
        return redirect('artist_list')
    
    return render(request, 'artists/artist_form.html', {'action': 'create'})


@raw_sql_login_required
def artist_update_view(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat mengubah artist.')
        return redirect('artist_list')
    
    # Fetch artist
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM artist WHERE artist_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        artist_row = cursor.fetchone()
        if not artist_row:
            messages.error(request, 'Artist tidak ditemukan.')
            return redirect('artist_list')
        artist = dict(zip(cols, artist_row))
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        genre = request.POST.get('genre', '').strip()
        
        if not name:
            messages.error(request, 'Nama artist wajib diisi.')
            return render(request, 'artists/artist_form.html', {'artist': artist, 'action': 'update'})
        
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE artist SET name = %s, genre = %s WHERE artist_id = %s",
                [name, genre or None, pk]
            )
        
        messages.success(request, 'Artist berhasil diperbarui.')
        return redirect('artist_list')
    
    return render(request, 'artists/artist_form.html', {'artist': artist, 'action': 'update'})


@raw_sql_login_required
def artist_delete_view(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat menghapus artist.')
        return redirect('artist_list')
    
    # Fetch artist
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM artist WHERE artist_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        artist_row = cursor.fetchone()
        if not artist_row:
            messages.error(request, 'Artist tidak ditemukan.')
            return redirect('artist_list')
        artist = dict(zip(cols, artist_row))
    
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM artist WHERE artist_id = %s", [pk])
        
        messages.success(request, 'Artist berhasil dihapus.')
        return redirect('artist_list')
    
    return render(request, 'artists/artist_confirm_delete.html', {'artist': artist})
