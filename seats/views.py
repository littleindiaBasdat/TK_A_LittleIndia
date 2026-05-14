from django.contrib import messages
from accounts.middleware import raw_sql_login_required
from django.shortcuts import redirect, render
from django.db import connection


def can_manage(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


@raw_sql_login_required
def seat_list_view(request):
    query = request.GET.get('q', '').strip()
    venue_filter = request.GET.get('venue', '').strip()
    status_filter = request.GET.get('status', '').strip()

    # Build SQL query
    # FIX: kolom di DB adalah seat_number dan row_number (sesuai DDL)
    sql = """
        SELECT s.*, v.venue_name as venue_name
        FROM seat s
        LEFT JOIN venue v ON s.venue_id = v.venue_id
        WHERE 1=1
    """
    params = []

    # Query filter
    if query:
        sql += """ AND (LOWER(s.section) LIKE LOWER(%s)
                      OR LOWER(s.row_number) LIKE LOWER(%s)
                      OR LOWER(s.seat_number) LIKE LOWER(%s)
                      OR LOWER(v.venue_name) LIKE LOWER(%s))"""
        params.extend([f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"])

    # Venue filter
    if venue_filter:
        sql += " AND s.venue_id = %s"
        params.append(venue_filter)

    # FIX: relasi seat <-> ticket lewat HAS_RELATIONSHIP, bukan kolom seat_id di ticket
    if status_filter == 'filled':
        sql += " AND s.seat_id IN (SELECT DISTINCT seat_id FROM has_relationship)"
    elif status_filter == 'available':
        sql += " AND s.seat_id NOT IN (SELECT DISTINCT seat_id FROM has_relationship)"

    # Fetch seats
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        seats = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Fetch set of filled seat_ids dari has_relationship
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT seat_id FROM has_relationship")
        filled_ids = {str(row[0]) for row in cursor.fetchall()}

    # Tandai setiap seat apakah terisi atau tidak
    for seat in seats:
        seat['is_filled'] = str(seat['seat_id']) in filled_ids

    # Fetch venues
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM venue ORDER BY venue_name")
        cols = [col[0] for col in cursor.description]
        venues = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Calculate statistics (overall, not filtered)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM seat")
        total = cursor.fetchone()[0]
    filled = len(filled_ids)
    available = max(total - filled, 0)

    return render(request, 'seats/seat_list.html', {
        'seats': seats,
        'venues': venues,
        'query': query,
        'venue_filter': venue_filter,
        'status_filter': status_filter,
        'total': total,
        'filled': filled,
        'available': available,
        'can_manage': can_manage(request.user),
    })


@raw_sql_login_required
def seat_create_view(request):
    if not can_manage(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk menambah kursi.')
        return redirect('seat_list')

    # Fetch venues
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM venue ORDER BY venue_name")
        cols = [col[0] for col in cursor.description]
        venues = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if request.method == 'POST':
        venue_id = request.POST.get('venue')
        section = request.POST.get('section', '').strip()
        # FIX: nama field form harus row_number & seat_number
        row_number = request.POST.get('row_number', '').strip()
        seat_number = request.POST.get('seat_number', '').strip()

        if not all([venue_id, section, row_number, seat_number]):
            messages.error(request, 'Semua field wajib diisi.')
        else:
            with connection.cursor() as cursor:
                # Check if venue exists
                cursor.execute("SELECT 1 FROM venue WHERE venue_id = %s", [venue_id])
                if not cursor.fetchone():
                    messages.error(request, 'Venue tidak ditemukan.')
                    return render(request, 'seats/seat_form.html', {'venues': venues, 'action': 'create'})

                # Check duplicate
                cursor.execute(
                    """SELECT 1 FROM seat
                       WHERE venue_id = %s AND section = %s
                         AND row_number = %s AND seat_number = %s""",
                    [venue_id, section, row_number, seat_number]
                )
                if cursor.fetchone():
                    messages.error(request, 'Kursi dengan kombinasi tersebut sudah ada.')
                    return render(request, 'seats/seat_form.html', {'venues': venues, 'action': 'create'})

                # Create seat
                cursor.execute(
                    """INSERT INTO seat (venue_id, section, row_number, seat_number)
                       VALUES (%s, %s, %s, %s)""",
                    [venue_id, section, row_number, seat_number]
                )

            messages.success(request, 'Kursi berhasil ditambahkan.')
            return redirect('seat_list')

    return render(request, 'seats/seat_form.html', {'venues': venues, 'action': 'create'})


@raw_sql_login_required
def seat_update_view(request, pk):
    if not can_manage(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah kursi.')
        return redirect('seat_list')

    # Fetch seat
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM seat WHERE seat_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        seat_row = cursor.fetchone()
        if not seat_row:
            messages.error(request, 'Kursi tidak ditemukan.')
            return redirect('seat_list')
        seat = dict(zip(cols, seat_row))

    # Fetch venues
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM venue ORDER BY venue_name")
        cols = [col[0] for col in cursor.description]
        venues = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if request.method == 'POST':
        venue_id = request.POST.get('venue')
        section = request.POST.get('section', '').strip()
        row_number = request.POST.get('row_number', '').strip()
        seat_number = request.POST.get('seat_number', '').strip()

        if not all([venue_id, section, row_number, seat_number]):
            messages.error(request, 'Semua field wajib diisi.')
        else:
            with connection.cursor() as cursor:
                # Check if venue exists
                cursor.execute("SELECT 1 FROM venue WHERE venue_id = %s", [venue_id])
                if not cursor.fetchone():
                    messages.error(request, 'Venue tidak ditemukan.')
                    return render(request, 'seats/seat_form.html', {'venues': venues, 'seat': seat, 'action': 'update'})

                # Check duplicate (excluding current)
                cursor.execute(
                    """SELECT 1 FROM seat
                       WHERE venue_id = %s AND section = %s
                         AND row_number = %s AND seat_number = %s
                         AND seat_id != %s""",
                    [venue_id, section, row_number, seat_number, pk]
                )
                if cursor.fetchone():
                    messages.error(request, 'Kursi dengan kombinasi tersebut sudah ada.')
                    return render(request, 'seats/seat_form.html', {'venues': venues, 'seat': seat, 'action': 'update'})

                # Update seat
                cursor.execute(
                    """UPDATE seat
                       SET venue_id = %s, section = %s,
                           row_number = %s, seat_number = %s
                       WHERE seat_id = %s""",
                    [venue_id, section, row_number, seat_number, pk]
                )

            messages.success(request, 'Kursi berhasil diperbarui.')
            return redirect('seat_list')

    return render(request, 'seats/seat_form.html', {'venues': venues, 'seat': seat, 'action': 'update'})


@raw_sql_login_required
def seat_delete_view(request, pk):
    if not can_manage(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk menghapus kursi.')
        return redirect('seat_list')

    # Fetch seat
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM seat WHERE seat_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        seat_row = cursor.fetchone()
        if not seat_row:
            messages.error(request, 'Kursi tidak ditemukan.')
            return redirect('seat_list')
        seat = dict(zip(cols, seat_row))

    if request.method == 'POST':
        # TODO: Abid (Trigger 5.1) - validasi kursi sudah di-assign ke tiket
        # (cek tabel has_relationship) akan di-handle oleh trigger BEFORE DELETE ON seat.
        # Pesan error trigger akan ditangkap oleh try/except di bawah ini.
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM seat WHERE seat_id = %s", [pk])
        except Exception as exc:
            messages.error(request, str(exc))
            return redirect('seat_list')
        messages.success(request, 'Kursi berhasil dihapus.')
        return redirect('seat_list')

    return render(request, 'seats/seat_confirm_delete.html', {'seat': seat})