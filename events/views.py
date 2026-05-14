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
    """Attach artists and ticket_categories lists to each event dict."""
    if not events:
        return events
    event_ids = [e['event_id'] for e in events]
    placeholders = ','.join(['%s'] * len(event_ids))

    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT ea.event_id, a.name, ea.role
                FROM event_artist ea
                JOIN artist a ON ea.artist_id = a.artist_id
                WHERE ea.event_id IN ({placeholders})
                ORDER BY a.name""",
            event_ids
        )
        artists_by_event = {}
        for ev_id, name, role in cursor.fetchall():
            artists_by_event.setdefault(ev_id, []).append({'name': name, 'role': role})

    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT event_id, category_id, category_name, price, quota
                FROM ticket_category
                WHERE event_id IN ({placeholders})
                ORDER BY price""",
            event_ids
        )
        categories_by_event = {}
        for ev_id, cat_id, cname, price, quota in cursor.fetchall():
            categories_by_event.setdefault(ev_id, []).append({
                'category_id': cat_id,
                'name': cname,
                'price': price,
                'quota': quota,
            })

    for e in events:
        e['artists'] = artists_by_event.get(e['event_id'], [])
        e['categories'] = categories_by_event.get(e['event_id'], [])
        e['min_price'] = min((c['price'] for c in e['categories']), default=None)
    return events


@raw_sql_login_required
def event_list_view(request):
    if not can_manage(request.user):
        messages.error(request, 'Hanya admin atau organizer yang dapat mengakses halaman ini.')
        return redirect('dashboard')

    sql = """
        SELECT e.event_id, e.event_title, e.event_datetime, e.description,
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
    query = request.GET.get('q', '').strip()
    venue_filter = request.GET.get('venue', '').strip()
    artist_filter = request.GET.get('artist', '').strip()

    sql = """
        SELECT DISTINCT e.event_id, e.event_title, e.event_datetime, e.description,
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
        event_date = request.POST.get('event_date', '').strip()
        event_time = request.POST.get('event_time', '').strip()
        venue_id = request.POST.get('venue', '').strip()
        organizer_id = request.POST.get('organizer', '').strip()
        description = request.POST.get('description', '').strip()
        artist_ids = request.POST.getlist('artists')
        cat_ids = request.POST.getlist('cat_id')
        cat_names = request.POST.getlist('cat_name')
        cat_prices = request.POST.getlist('cat_price')
        cat_quotas = request.POST.getlist('cat_quota')

        if request.user.role == 'organizer':
            organizer_id = str(_get_organizer_id(str(request.user.id)))

        event_datetime = f"{event_date} {event_time}:00" if event_date and event_time else ''

        error = _validate_event(event_title, event_date, event_time, venue_id, organizer_id)
        if error:
            messages.error(request, error)
        else:
            event_id = str(uuid.uuid4())
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO event
                               (event_id, event_title, event_datetime, venue_id, organizer_id, description)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        [event_id, event_title, event_datetime, venue_id, organizer_id, description or None]
                    )
                    for aid in artist_ids:
                        if aid:
                            cursor.execute(
                                "INSERT INTO event_artist (event_id, artist_id, role) VALUES (%s, %s, %s)",
                                [event_id, aid, 'Performer']
                            )
                    for cat_name, cat_price, cat_quota in zip(cat_names, cat_prices, cat_quotas):
                        cat_name = cat_name.strip()
                        if cat_name and cat_price and cat_quota:
                            cursor.execute(
                                """INSERT INTO ticket_category
                                       (category_id, category_name, quota, price, event_id)
                                   VALUES (%s, %s, %s, %s, %s)""",
                                [str(uuid.uuid4()), cat_name, int(cat_quota), float(cat_price), event_id]
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

    fetch_sql = """
        SELECT e.event_id, e.event_title, e.event_datetime, e.description,
               e.venue_id, e.organizer_id
        FROM event e
        WHERE e.event_id = %s
    """
    fetch_params = [pk]
    if request.user.role == 'organizer':
        fetch_sql += " AND e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)"
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

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT category_id, category_name, price, quota
               FROM ticket_category WHERE event_id = %s ORDER BY price""",
            [pk]
        )
        existing_categories = [
            dict(zip(['category_id', 'category_name', 'price', 'quota'], r))
            for r in cursor.fetchall()
        ]

    venues, organizers, artists = _fetch_form_options(request.user)

    if request.method == 'POST':
        event_title = request.POST.get('event_title', '').strip()
        event_date = request.POST.get('event_date', '').strip()
        event_time = request.POST.get('event_time', '').strip()
        venue_id = request.POST.get('venue', '').strip()
        organizer_id = request.POST.get('organizer', '').strip()
        description = request.POST.get('description', '').strip()
        artist_ids = request.POST.getlist('artists')
        cat_ids = request.POST.getlist('cat_id')
        cat_names = request.POST.getlist('cat_name')
        cat_prices = request.POST.getlist('cat_price')
        cat_quotas = request.POST.getlist('cat_quota')

        if request.user.role == 'organizer':
            organizer_id = str(event['organizer_id'])

        event_datetime = f"{event_date} {event_time}:00" if event_date and event_time else ''

        error = _validate_event(event_title, event_date, event_time, venue_id, organizer_id)
        if error:
            messages.error(request, error)
        else:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE event
                           SET event_title = %s, event_datetime = %s,
                               venue_id = %s, organizer_id = %s, description = %s
                           WHERE event_id = %s""",
                        [event_title, event_datetime, venue_id, organizer_id, description or None, pk]
                    )

                    # Sync artists
                    cursor.execute("DELETE FROM event_artist WHERE event_id = %s", [pk])
                    for aid in artist_ids:
                        if aid:
                            cursor.execute(
                                "INSERT INTO event_artist (event_id, artist_id, role) VALUES (%s, %s, %s)",
                                [pk, aid, 'Performer']
                            )

                    # Sync ticket categories:
                    # - submitted with cat_id → UPDATE existing
                    # - submitted without cat_id → INSERT new
                    # - existing not submitted → DELETE (only if no tickets reference them)
                    existing_id_set = {str(c['category_id']) for c in existing_categories}
                    submitted_id_set = {cid for cid in cat_ids if cid}

                    for cid in existing_id_set - submitted_id_set:
                        cursor.execute(
                            """DELETE FROM ticket_category
                               WHERE category_id = %s
                               AND NOT EXISTS (SELECT 1 FROM ticket WHERE category_id = %s)""",
                            [cid, cid]
                        )

                    for cat_id, cat_name, cat_price, cat_quota in zip(
                        cat_ids, cat_names, cat_prices, cat_quotas
                    ):
                        cat_name = cat_name.strip()
                        if not (cat_name and cat_price and cat_quota):
                            continue
                        try:
                            quota = int(cat_quota)
                            price = float(cat_price)
                        except ValueError:
                            continue
                        if cat_id:
                            cursor.execute(
                                """UPDATE ticket_category
                                   SET category_name = %s, price = %s, quota = %s
                                   WHERE category_id = %s""",
                                [cat_name, price, quota, cat_id]
                            )
                        else:
                            cursor.execute(
                                """INSERT INTO ticket_category
                                       (category_id, category_name, quota, price, event_id)
                                   VALUES (%s, %s, %s, %s, %s)""",
                                [str(uuid.uuid4()), cat_name, quota, price, pk]
                            )

            except Exception as exc:
                messages.error(request, str(exc))
                return render(request, 'events/event_form.html', {
                    'event': event, 'venues': venues, 'organizers': organizers,
                    'artists': artists, 'existing_artist_ids': existing_artist_ids,
                    'existing_categories': existing_categories, 'action': 'update',
                })

            messages.success(request, 'Event berhasil diperbarui.')
            return redirect('event_list')

    return render(request, 'events/event_form.html', {
        'event': event,
        'venues': venues,
        'organizers': organizers,
        'artists': artists,
        'existing_artist_ids': existing_artist_ids,
        'existing_categories': existing_categories,
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


def _validate_event(event_title, event_date, event_time, venue_id, organizer_id):
    if not event_title:
        return 'Judul acara wajib diisi.'
    if not event_date or not event_time:
        return 'Tanggal dan waktu acara wajib diisi.'
    if not venue_id:
        return 'Venue wajib dipilih.'
    if not organizer_id:
        return 'Organizer wajib dipilih.'
    return None
