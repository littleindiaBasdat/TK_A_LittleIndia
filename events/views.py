import uuid
from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import connection
from accounts.middleware import raw_sql_login_required


def can_manage(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


def _get_organizer_id(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT organizer_id FROM organizer WHERE user_id = %s", [user_id])
        row = cursor.fetchone()
    return row[0] if row else None


def _fetch_event_with_relations(events):
    """Add 'artists' and 'categories' list to each event dict."""
    if not events:
        return events
    event_ids = [e['event_id'] for e in events]
    placeholders = ','.join(['%s'] * len(event_ids))

    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT ea.event_id, a.name, ea.role
                FROM event_artist ea
                JOIN artist a ON ea.artist_id = a.artist_id
                WHERE ea.event_id IN ({placeholders})""",
            event_ids
        )
        artists_by_event = {}
        for ev_id, name, role in cursor.fetchall():
            artists_by_event.setdefault(ev_id, []).append({'name': name, 'role': role})

    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT event_id, category_name, price
                FROM ticket_category
                WHERE event_id IN ({placeholders})
                ORDER BY price""",
            event_ids
        )
        categories_by_event = {}
        for ev_id, cname, price in cursor.fetchall():
            categories_by_event.setdefault(ev_id, []).append({'name': cname, 'price': price})

    for e in events:
        e['artists'] = artists_by_event.get(e['event_id'], [])
        e['categories'] = categories_by_event.get(e['event_id'], [])
        e['min_price'] = min((c['price'] for c in e['categories']), default=None)
    return events


@raw_sql_login_required
def event_list_view(request):
    """For Admin & Organizer ('Event Saya' page)."""
    if not can_manage(request.user):
        messages.error(request, 'Hanya admin atau organizer yang dapat mengakses halaman ini.')
        return redirect('dashboard')

    sql = """
        SELECT e.event_id, e.event_title, e.event_datetime,
               v.venue_name, v.city,
               o.organizer_name
        FROM event e
        LEFT JOIN venue v ON e.venue_id = v.venue_id
        LEFT JOIN organizer o ON e.organizer_id = o.organizer_id
        WHERE 1=1
    """
    params = []

    if request.user.role == 'organizer':
        sql += " AND e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)"
        params.append(str(request.user.id))

    sql += " ORDER BY e.event_datetime DESC"

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        events = [dict(zip(cols, row)) for row in cursor.fetchall()]

    events = _fetch_event_with_relations(events)

    return render(request, 'events/event_list.html', {
        'events': events,
        'can_manage': True,
    })


def event_browse_view(request):
    """For Customers & all users ('Cari Event' page)."""
    query = request.GET.get('q', '').strip()
    venue_filter = request.GET.get('venue', '').strip()
    artist_filter = request.GET.get('artist', '').strip()

    sql = """
        SELECT DISTINCT e.event_id, e.event_title, e.event_datetime,
               v.venue_name, v.city,
               o.organizer_name
        FROM event e
        LEFT JOIN venue v ON e.venue_id = v.venue_id
        LEFT JOIN organizer o ON e.organizer_id = o.organizer_id
        LEFT JOIN event_artist ea ON e.event_id = ea.event_id
        LEFT JOIN artist a ON ea.artist_id = a.artist_id
        WHERE 1=1
    """
    params = []

    if query:
        sql += " AND (LOWER(e.event_title) LIKE LOWER(%s) OR LOWER(a.name) LIKE LOWER(%s))"
        params.extend([f"%{query}%", f"%{query}%"])

    if venue_filter:
        sql += " AND e.venue_id = %s"
        params.append(venue_filter)

    if artist_filter:
        sql += " AND ea.artist_id = %s"
        params.append(artist_filter)

    sql += " ORDER BY e.event_datetime ASC"

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        events = [dict(zip(cols, row)) for row in cursor.fetchall()]

    events = _fetch_event_with_relations(events)

    with connection.cursor() as cursor:
        cursor.execute("SELECT venue_id, venue_name FROM venue ORDER BY venue_name")
        venues = [{'id': r[0], 'name': r[1]} for r in cursor.fetchall()]
        cursor.execute("SELECT artist_id, name FROM artist ORDER BY name")
        artists = [{'id': r[0], 'name': r[1]} for r in cursor.fetchall()]

    can_buy = request.user.is_authenticated and request.user.role == 'customer'

    return render(request, 'events/event_browse.html', {
        'events': events,
        'venues': venues,
        'artists': artists,
        'query': query,
        'venue_filter': venue_filter,
        'artist_filter': artist_filter,
        'can_buy': can_buy,
    })


@raw_sql_login_required
def event_create_view(request):
    if not can_manage(request.user):
        messages.error(request, 'Hanya admin atau organizer yang dapat membuat event.')
        return redirect('event_list')

    venues, organizers, artists = _fetch_form_options(request.user)

    if request.method == 'POST':
        event_title = request.POST.get('event_title', '').strip()
        event_datetime = request.POST.get('event_datetime', '').strip()
        venue_id = request.POST.get('venue', '').strip()
        organizer_id = request.POST.get('organizer', '').strip()
        artist_ids = request.POST.getlist('artists')

        if request.user.role == 'organizer':
            organizer_id = _get_organizer_id(str(request.user.id))

        error = _validate_event(event_title, event_datetime, venue_id, organizer_id)
        if error:
            messages.error(request, error)
        else:
            event_id = str(uuid.uuid4())
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO event (event_id, event_title, event_datetime, venue_id, organizer_id)
                           VALUES (%s, %s, %s, %s, %s)""",
                        [event_id, event_title, event_datetime, venue_id, organizer_id]
                    )
                    # TODO: Ammar (Trigger 3.1) - validasi duplikasi (event_id, artist_id)
                    # & eksistensi artist/event akan di-handle oleh trigger BEFORE INSERT
                    # ON event_artist. Pesan error trigger akan ditangkap di except di bawah.
                    for aid in artist_ids:
                        cursor.execute(
                            "INSERT INTO event_artist (event_id, artist_id, role) VALUES (%s, %s, %s)",
                            [event_id, aid, 'Performer']
                        )
            except Exception as exc:
                messages.error(request, str(exc))
                return render(request, 'events/event_form.html', {
                    'venues': venues, 'organizers': organizers, 'artists': artists,
                    'action': 'create',
                })

            messages.success(request, 'Event berhasil dibuat.')
            return redirect('event_list')

    return render(request, 'events/event_form.html', {
        'venues': venues,
        'organizers': organizers,
        'artists': artists,
        'action': 'create',
    })


@raw_sql_login_required
def event_update_view(request, pk):
    if not can_manage(request.user):
        messages.error(request, 'Hanya admin atau organizer yang dapat mengubah event.')
        return redirect('event_list')

    fetch_sql = "SELECT * FROM event WHERE event_id = %s"
    fetch_params = [pk]
    if request.user.role == 'organizer':
        fetch_sql += " AND organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)"
        fetch_params.append(str(request.user.id))

    with connection.cursor() as cursor:
        cursor.execute(fetch_sql, fetch_params)
        cols = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        if not row:
            messages.error(request, 'Event tidak ditemukan atau Anda tidak punya akses.')
            return redirect('event_list')
        event = dict(zip(cols, row))

    with connection.cursor() as cursor:
        cursor.execute("SELECT artist_id FROM event_artist WHERE event_id = %s", [pk])
        existing_artist_ids = [str(r[0]) for r in cursor.fetchall()]

    venues, organizers, artists = _fetch_form_options(request.user)

    if request.method == 'POST':
        event_title = request.POST.get('event_title', '').strip()
        event_datetime = request.POST.get('event_datetime', '').strip()
        venue_id = request.POST.get('venue', '').strip()
        organizer_id = request.POST.get('organizer', '').strip()
        artist_ids = request.POST.getlist('artists')

        if request.user.role == 'organizer':
            organizer_id = str(event['organizer_id'])

        error = _validate_event(event_title, event_datetime, venue_id, organizer_id)
        if error:
            messages.error(request, error)
        else:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE event SET event_title = %s, event_datetime = %s,
                                            venue_id = %s, organizer_id = %s
                           WHERE event_id = %s""",
                        [event_title, event_datetime, venue_id, organizer_id, pk]
                    )
                    cursor.execute("DELETE FROM event_artist WHERE event_id = %s", [pk])
                    # TODO: Ammar (Trigger 3.1) - validasi duplikasi (event_id, artist_id)
                    # & eksistensi artist/event di-handle oleh trigger BEFORE INSERT ON event_artist.
                    for aid in artist_ids:
                        cursor.execute(
                            "INSERT INTO event_artist (event_id, artist_id, role) VALUES (%s, %s, %s)",
                            [pk, aid, 'Performer']
                        )
            except Exception as exc:
                messages.error(request, str(exc))
                return render(request, 'events/event_form.html', {
                    'event': event, 'venues': venues, 'organizers': organizers,
                    'artists': artists, 'existing_artist_ids': existing_artist_ids,
                    'action': 'update',
                })

            messages.success(request, 'Event berhasil diperbarui.')
            return redirect('event_list')

    return render(request, 'events/event_form.html', {
        'event': event,
        'venues': venues,
        'organizers': organizers,
        'artists': artists,
        'existing_artist_ids': existing_artist_ids,
        'action': 'update',
    })


def _fetch_form_options(user):
    with connection.cursor() as cursor:
        cursor.execute("SELECT venue_id, venue_name, city FROM venue ORDER BY venue_name")
        venues = [dict(zip(['venue_id', 'venue_name', 'city'], r)) for r in cursor.fetchall()]

        if user.role == 'admin':
            cursor.execute("SELECT organizer_id, organizer_name FROM organizer ORDER BY organizer_name")
            organizers = [dict(zip(['organizer_id', 'organizer_name'], r)) for r in cursor.fetchall()]
        else:
            organizers = []

        cursor.execute("SELECT artist_id, name FROM artist ORDER BY name")
        artists = [dict(zip(['artist_id', 'name'], r)) for r in cursor.fetchall()]

    return venues, organizers, artists


def _validate_event(event_title, event_datetime, venue_id, organizer_id):
    if not all([event_title, event_datetime, venue_id, organizer_id]):
        return 'Semua field wajib diisi (judul, tanggal/waktu, venue, organizer).'
    return None
