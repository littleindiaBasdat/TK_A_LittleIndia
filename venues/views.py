import uuid
from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import connection
from accounts.middleware import raw_sql_login_required


def can_manage(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


def _pg_error_message(exc):
    cause = getattr(exc, '__cause__', None)
    if cause is not None:
        diag = getattr(cause, 'diag', None)
        if diag is not None and diag.message_primary:
            return diag.message_primary
    return str(exc).split('\nCONTEXT:')[0].split(' CONTEXT:')[0].strip()


def venue_list_view(request):
    query = request.GET.get('q', '').strip()
    city_filter = request.GET.get('city', '').strip()
    seating_filter = request.GET.get('seating', '').strip()

    sql = "SELECT venue_id, venue_name, address, city, capacity, has_reserved_seating FROM venue WHERE 1=1"
    params = []

    if query:
        sql += " AND (LOWER(venue_name) LIKE LOWER(%s) OR LOWER(address) LIKE LOWER(%s))"
        params.extend([f"%{query}%", f"%{query}%"])

    if city_filter:
        sql += " AND city = %s"
        params.append(city_filter)

    if seating_filter == 'reserved':
        sql += " AND has_reserved_seating = TRUE"
    elif seating_filter == 'free':
        sql += " AND has_reserved_seating = FALSE"

    sql += " ORDER BY venue_name"

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        venues = [dict(zip(cols, row)) for row in cursor.fetchall()]

    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT city FROM venue ORDER BY city")
        cities = [row[0] for row in cursor.fetchall()]

    return render(request, 'venues/venue_list.html', {
        'venues': venues,
        'cities': cities,
        'query': query,
        'city_filter': city_filter,
        'seating_filter': seating_filter,
        'can_manage': can_manage(request.user),
    })


@raw_sql_login_required
def venue_create_view(request):
    if not can_manage(request.user):
        messages.error(request, 'Hanya admin atau organizer yang dapat menambah venue.')
        return redirect('venue_list')

    if request.method == 'POST':
        venue_name = request.POST.get('venue_name', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        capacity_raw = request.POST.get('capacity', '')
        has_reserved_seating = request.POST.get('has_reserved_seating') == 'on'

        error = _validate_fields(venue_name, address, city, capacity_raw)
        if error:
            messages.error(request, error)
            return render(request, 'venues/venue_form.html', {
                'action': 'create',
                'venue': {
                    'venue_name': venue_name, 'address': address,
                    'city': city, 'capacity': capacity_raw,
                    'has_reserved_seating': has_reserved_seating,
                },
            })

        venue_id = str(uuid.uuid4())
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO venue (venue_id, venue_name, address, city, capacity, has_reserved_seating)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    [venue_id, venue_name, address, city, int(capacity_raw), has_reserved_seating]
                )
        except Exception as exc:
            messages.error(request, _pg_error_message(exc))
            return render(request, 'venues/venue_form.html', {
                'action': 'create',
                'venue': {
                    'venue_name': venue_name, 'address': address,
                    'city': city, 'capacity': capacity_raw,
                    'has_reserved_seating': has_reserved_seating,
                },
            })

        messages.success(request, 'Venue berhasil ditambahkan.')
        return redirect('venue_list')

    return render(request, 'venues/venue_form.html', {'action': 'create'})


@raw_sql_login_required
def venue_update_view(request, pk):
    if not can_manage(request.user):
        messages.error(request, 'Hanya admin atau organizer yang dapat mengubah venue.')
        return redirect('venue_list')

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT venue_id, venue_name, address, city, capacity, has_reserved_seating FROM venue WHERE venue_id = %s",
            [pk]
        )
        cols = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        if not row:
            messages.error(request, 'Venue tidak ditemukan.')
            return redirect('venue_list')
        venue = dict(zip(cols, row))

    if request.method == 'POST':
        venue_name = request.POST.get('venue_name', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        capacity_raw = request.POST.get('capacity', '')
        has_reserved_seating = request.POST.get('has_reserved_seating') == 'on'

        error = _validate_fields(venue_name, address, city, capacity_raw)
        if error:
            messages.error(request, error)
            return render(request, 'venues/venue_form.html', {'venue': venue, 'action': 'update'})

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE venue SET venue_name = %s, address = %s, city = %s,
                              capacity = %s, has_reserved_seating = %s
                       WHERE venue_id = %s""",
                    [venue_name, address, city, int(capacity_raw), has_reserved_seating, pk]
                )
        except Exception as exc:
            messages.error(request, _pg_error_message(exc))
            return render(request, 'venues/venue_form.html', {'venue': venue, 'action': 'update'})

        messages.success(request, 'Venue berhasil diperbarui.')
        return redirect('venue_list')

    return render(request, 'venues/venue_form.html', {'venue': venue, 'action': 'update'})


@raw_sql_login_required
def venue_delete_view(request, pk):
    if not can_manage(request.user):
        messages.error(request, 'Hanya admin atau organizer yang dapat menghapus venue.')
        return redirect('venue_list')

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT venue_id, venue_name, address, city, capacity, has_reserved_seating FROM venue WHERE venue_id = %s",
            [pk]
        )
        cols = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        if not row:
            messages.error(request, 'Venue tidak ditemukan.')
            return redirect('venue_list')
        venue = dict(zip(cols, row))

    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM venue WHERE venue_id = %s", [pk])
        except Exception as exc:
            messages.error(request, _pg_error_message(exc))
            return redirect('venue_list')

        messages.success(request, 'Venue berhasil dihapus.')
        return redirect('venue_list')

    return render(request, 'venues/venue_confirm_delete.html', {'venue': venue})


def _validate_fields(venue_name, address, city, capacity_raw):
    if not all([venue_name, address, city, capacity_raw]):
        return 'Semua field wajib diisi.'
    try:
        if int(capacity_raw) <= 0:
            return 'Kapasitas harus lebih dari 0.'
    except ValueError:
        return 'Kapasitas harus berupa angka.'
    return None
