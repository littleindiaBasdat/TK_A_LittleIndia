import uuid
from django.contrib import messages
from accounts.middleware import raw_sql_login_required
from django.shortcuts import redirect, render
from django.db import connection


def can_create(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


def can_admin(user):
    return user.is_authenticated and user.role == 'admin'


def get_ticket_status_column():
    """Return a safe status column name for ticket table, if exists."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'ticket'
              AND column_name IN ('status', 'ticket_status')
            """
        )
        row = cursor.fetchone()
    return row[0] if row else None


def scoped_tickets(user):
    """Returns SQL WHERE clause and params for ticket scoping"""
    # FIX: user.id seharusnya pakai user_id dari session (sesuai middleware)
    user_id = str(user.id)
    user_role = user.role

    if user_role == 'customer':
        # scope: tiket milik customer yang sedang login
        return " AND c.user_id = %s", [user_id]
    elif user_role == 'organizer':
        # scope: tiket dari event yang diorganize
        # NOTE: user.id = user_id; organizer_id harus dilookup dari tabel organizer
        return " AND e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)", [user_id]
    return "", []


def category_scope(user):
    """Returns SQL WHERE clause and params for category scoping"""
    if not getattr(user, 'is_authenticated', False):
        return "", []
    user_id = str(user.id)
    user_role = user.role

    if user_role == 'organizer':
        return " AND e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)", [user_id]
    return "", []


def event_scope(user):
    """Returns SQL WHERE clause and params for event scoping"""
    if not getattr(user, 'is_authenticated', False):
        return "", []
    user_id = str(user.id)
    user_role = user.role

    if user_role == 'organizer':
        return " AND organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)", [user_id]
    return "", []


def can_manage_category(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


# ============================================================
# TICKET VIEWS
# ============================================================

@raw_sql_login_required
def ticket_list_view(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    status_col = get_ticket_status_column()

    # FIX: kolom di DB:
    #   ticket       -> ticket_id, ticket_code, category_id, order_id  (TIDAK ada status, seat_id)
    #   ticket_category -> category_id, category_name, quota, price, event_id
    #   event        -> event_id, event_title, venue_id, organizer_id
    #   customer     -> customer_id, full_name, user_id
    #   "ORDER"      -> order_id, order_date, payment_status, total_amount, customer_id
    #   has_relationship -> ticket_id, seat_id  (relasi ticket <-> seat)
    #   seat         -> seat_id, section, row_number, seat_number, venue_id
    select_status = f", t.{status_col} AS ticket_status" if status_col else ""
    sql = f"""
        SELECT
            t.ticket_id,
            t.ticket_code,
            t.category_id,
            t.order_id,
            o.customer_id,
            c.full_name        AS customer_name,
            tc.category_name,
            tc.price           AS category_price,
            e.event_id,
            e.event_title,
            e.event_datetime,
            v.venue_name,
            hr.seat_id,
            s.section          AS seat_section,
            s.row_number       AS seat_row,
            s.seat_number      AS seat_number
            {select_status}
        FROM ticket t
        LEFT JOIN "ORDER" o   ON t.order_id    = o.order_id
        LEFT JOIN customer c  ON o.customer_id = c.customer_id
        LEFT JOIN ticket_category tc ON t.category_id = tc.category_id
        LEFT JOIN event e     ON tc.event_id   = e.event_id
        LEFT JOIN venue v     ON e.venue_id    = v.venue_id
        LEFT JOIN has_relationship hr ON t.ticket_id = hr.ticket_id
        LEFT JOIN seat s      ON hr.seat_id    = s.seat_id
        WHERE 1=1
    """
    params = []

    # Apply user scope
    scope_clause, scope_params = scoped_tickets(request.user)
    sql += scope_clause
    params.extend(scope_params)

    # Query filter
    if query:
        sql += " AND (LOWER(t.ticket_code) LIKE LOWER(%s) OR LOWER(e.event_title) LIKE LOWER(%s))"
        params.extend([f"%{query}%", f"%{query}%"])

    if status_filter and status_col:
        sql += f" AND t.{status_col} = %s"
        params.append(status_filter)

    # Fetch tickets
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        tickets = [dict(zip(cols, row)) for row in cursor.fetchall()]

    status_options = []
    if status_col:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT DISTINCT t.{status_col} FROM ticket t WHERE t.{status_col} IS NOT NULL ORDER BY 1"
            )
            status_options = [row[0] for row in cursor.fetchall()]

    total_count = len(tickets)
    valid_count = 0
    used_count = 0
    for ticket in tickets:
        status_value = ticket.get('ticket_status') if status_col else None
        status_text = (str(status_value).strip().lower() if status_value is not None else '')
        if not status_col:
            valid_count += 1
        elif status_text in ['valid', 'aktif', 'active']:
            valid_count += 1
        elif status_text in ['terpakai', 'used', 'checkedin', 'redeemed']:
            used_count += 1

    title = 'Tiket Saya' if request.user.role == 'customer' else 'Manajemen Tiket'
    return render(request, 'tickets/ticket_list.html', {
        'tickets': tickets,
        'query': query,
        'status_filter': status_filter,
        'status_options': status_options,
        'total_count': total_count,
        'valid_count': valid_count,
        'used_count': used_count,
        'title': title,
        'can_create': can_create(request.user),
        'can_admin': can_admin(request.user),
    })


@raw_sql_login_required
def ticket_create_view(request):
    if not can_create(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk membuat tiket.')
        return redirect('ticket_list')

    # Get orders with event info via ticket_category
    # NOTE: order yang belum punya tiket -> event_title NULL. Itu OK, ditampilkan "-"
    orders_sql = """
        SELECT o.order_id, o.order_date, o.payment_status, o.total_amount,
               c.full_name AS customer_name,
               MIN(tc.event_id::text) AS event_id,
               MIN(e.event_title) AS event_title,
               MIN(e.venue_id::text) AS venue_id
        FROM "ORDER" o
        LEFT JOIN customer c ON o.customer_id = c.customer_id
        LEFT JOIN ticket t ON o.order_id = t.order_id
        LEFT JOIN ticket_category tc ON t.category_id = tc.category_id
        LEFT JOIN event e ON tc.event_id = e.event_id
        LEFT JOIN venue v ON e.venue_id = v.venue_id
        WHERE 1=1
    """
    orders_params = []

    if request.user.role == 'organizer':
        orders_sql += """ AND o.order_id IN (
            SELECT DISTINCT t.order_id FROM ticket t
            JOIN ticket_category tc ON t.category_id = tc.category_id
            WHERE tc.event_id IN (
                SELECT e.event_id FROM event e
                WHERE e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)
            )
        )"""
        orders_params.append(str(request.user.id))

    orders_sql += """ GROUP BY o.order_id, o.order_date, o.payment_status, o.total_amount, c.full_name
        ORDER BY o.order_date DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(orders_sql, orders_params)
        cols = [col[0] for col in cursor.description]
        orders = [dict(zip(cols, row)) for row in cursor.fetchall()]

    venue_ids = [o.get('venue_id') for o in orders if o.get('venue_id')]
    seat_counts = {}
    if venue_ids:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT venue_id::text, COUNT(*)
                   FROM seat
                   WHERE venue_id::text = ANY(%s)
                   GROUP BY venue_id::text""",
                [venue_ids]
            )
            seat_counts = {row[0]: row[1] for row in cursor.fetchall()}

    for order in orders:
        venue_id = order.get('venue_id')
        order['has_reserved_seating'] = bool(seat_counts.get(str(venue_id), 0))

    # Get categories with quota usage info
    # TODO: Ammar (Trigger 3.2) - bisa diganti pakai stored function sisa kuota
    # berdasarkan event_id (lihat spec No. 3.2). Kalau fungsi sudah ready,
    # gunakan: SELECT * FROM get_remaining_quota_by_event(<event_id>);
    categories_sql = """
        SELECT tc.category_id, tc.category_name, tc.quota, tc.price,
               tc.event_id, e.event_title, v.venue_name, v.venue_id,
               COUNT(t.ticket_id) AS tickets_sold
        FROM ticket_category tc
        LEFT JOIN event e ON tc.event_id = e.event_id
        LEFT JOIN venue v ON e.venue_id = v.venue_id
        LEFT JOIN ticket t ON tc.category_id = t.category_id
        WHERE 1=1
    """
    categories_params = []

    if request.user.role == 'organizer':
        categories_sql += " AND e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)"
        categories_params.append(str(request.user.id))
    
    categories_sql += " GROUP BY tc.category_id, tc.category_name, tc.quota, tc.price, tc.event_id, e.event_title, v.venue_name, v.venue_id"

    with connection.cursor() as cursor:
        cursor.execute(categories_sql, categories_params)
        cols = [col[0] for col in cursor.description]
        categories = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Get available seats (not assigned to any ticket), include venue for filtering
    seats_sql = """
        SELECT s.seat_id, s.section, s.row_number, s.seat_number, s.venue_id, v.venue_name
        FROM seat s
        LEFT JOIN venue v ON s.venue_id = v.venue_id
        WHERE s.seat_id NOT IN (SELECT DISTINCT seat_id FROM has_relationship)
        ORDER BY v.venue_name, s.section, s.row_number, s.seat_number
    """

    with connection.cursor() as cursor:
        cursor.execute(seats_sql)
        cols = [col[0] for col in cursor.description]
        seats = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if request.method == 'POST':
        order_id = request.POST.get('order')
        category_id = request.POST.get('category')
        seat_id = request.POST.get('seat') or None

        if not all([order_id, category_id]):
            messages.error(request, 'Order dan kategori tiket wajib dipilih.')
        else:
            # TODO: Abid (Trigger 5.2) - validasi kuota kategori tiket (tickets_sold >= quota)
            # akan di-handle oleh trigger BEFORE INSERT ON ticket. Pesan error trigger
            # akan ditangkap oleh try/except di bawah ini.
            try:
                with connection.cursor() as cursor:
                    # Basic FK existence check (cepat di Python untuk UX yang ramah).
                    # Constraint sebenarnya tetap di-enforce oleh DB.
                    cursor.execute('SELECT order_id FROM "ORDER" WHERE order_id = %s', [order_id])
                    if not cursor.fetchone():
                        messages.error(request, 'Order tidak ditemukan.')
                        return render(request, 'tickets/ticket_form.html', {
                            'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                        })

                    cursor.execute(
                        "SELECT category_id, event_id FROM ticket_category WHERE category_id = %s",
                        [category_id]
                    )
                    cat_row = cursor.fetchone()
                    if not cat_row:
                        messages.error(request, 'Kategori tiket tidak valid.')
                        return render(request, 'tickets/ticket_form.html', {
                            'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                        })
                    category_event_id = str(cat_row[1]) if cat_row[1] else None

                    cursor.execute(
                        """SELECT MIN(tc.event_id::text) AS event_id, MIN(e.venue_id::text) AS venue_id
                           FROM ticket t
                           LEFT JOIN ticket_category tc ON t.category_id = tc.category_id
                           LEFT JOIN event e ON tc.event_id = e.event_id
                           LEFT JOIN venue v ON e.venue_id = v.venue_id
                           WHERE t.order_id = %s""",
                        [order_id]
                    )
                    order_event_row = cursor.fetchone()
                    order_event_id = str(order_event_row[0]) if order_event_row and order_event_row[0] else None
                    order_venue_id = str(order_event_row[1]) if order_event_row and order_event_row[1] else None
                    order_has_seats = False
                    if order_venue_id:
                        cursor.execute(
                            "SELECT 1 FROM seat WHERE venue_id = %s LIMIT 1",
                            [order_venue_id]
                        )
                        order_has_seats = cursor.fetchone() is not None

                    if order_event_id and category_event_id and order_event_id != category_event_id:
                        messages.error(request, 'Kategori tiket tidak sesuai dengan event pada order.')
                        return render(request, 'tickets/ticket_form.html', {
                            'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                        })

                    if seat_id and not order_has_seats:
                        messages.error(request, 'Event ini tidak menggunakan reserved seating.')
                        return render(request, 'tickets/ticket_form.html', {
                            'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                        })

                    if seat_id:
                        cursor.execute(
                            "SELECT seat_id FROM seat WHERE seat_id = %s AND (%s IS NULL OR venue_id = %s)",
                            [seat_id, order_venue_id, order_venue_id]
                        )
                        if not cursor.fetchone():
                            messages.error(request, 'Seat tidak valid.')
                            return render(request, 'tickets/ticket_form.html', {
                                'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                            })

                        cursor.execute(
                            "SELECT 1 FROM has_relationship WHERE seat_id = %s",
                            [seat_id]
                        )
                        if cursor.fetchone():
                            messages.error(request, 'Seat sudah terpakai.')
                            return render(request, 'tickets/ticket_form.html', {
                                'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                            })

                    # INSERT ticket - Trigger 5.2 (Abid) akan fire di sini untuk validasi kuota
                    ticket_id = str(uuid.uuid4())
                    code = f'TKT-{uuid.uuid4().hex[:10].upper()}'
                    cursor.execute(
                        """INSERT INTO ticket (ticket_id, ticket_code, category_id, order_id)
                           VALUES (%s, %s, %s, %s)""",
                        [ticket_id, code, category_id, order_id]
                    )

                    if seat_id:
                        cursor.execute(
                            "INSERT INTO has_relationship (ticket_id, seat_id) VALUES (%s, %s)",
                            [ticket_id, seat_id]
                        )
            except Exception as exc:
                messages.error(request, str(exc))
                return render(request, 'tickets/ticket_form.html', {
                    'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                })

            messages.success(request, 'Tiket berhasil dibuat.')
            return redirect('ticket_list')

    return render(request, 'tickets/ticket_form.html', {
        'orders': orders,
        'categories': categories,
        'seats': seats,
        'action': 'create',
    })


@raw_sql_login_required
def ticket_update_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat mengubah tiket.')
        return redirect('ticket_list')

    status_col = get_ticket_status_column()

    # FIX: fetch ticket + seat via has_relationship
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT t.*,
                      hr.seat_id,
                      s.venue_id AS seat_venue_id
               FROM ticket t
               LEFT JOIN has_relationship hr ON t.ticket_id = hr.ticket_id
               LEFT JOIN seat s ON hr.seat_id = s.seat_id
               WHERE t.ticket_id = %s""",
            [pk]
        )
        cols = [col[0] for col in cursor.description]
        ticket_row = cursor.fetchone()
        if not ticket_row:
            messages.error(request, 'Tiket tidak ditemukan.')
            return redirect('ticket_list')
        ticket = dict(zip(cols, ticket_row))

    # Fetch available seats (belum dipasang ke tiket lain, atau seat milik tiket ini)
    current_seat_id = ticket.get('seat_id')
    seats_sql = """
        SELECT s.*, v.venue_name AS venue_name
        FROM seat s
        LEFT JOIN venue v ON s.venue_id = v.venue_id
        WHERE s.seat_id NOT IN (SELECT DISTINCT seat_id FROM has_relationship WHERE ticket_id != %s)
           OR s.seat_id = %s
    """

    with connection.cursor() as cursor:
        cursor.execute(seats_sql, [pk, current_seat_id or '00000000-0000-0000-0000-000000000000'])
        cols = [col[0] for col in cursor.description]
        seats = [dict(zip(cols, row)) for row in cursor.fetchall()]

    status_options = []
    ticket_status_value = None
    if status_col:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT DISTINCT t.{status_col} FROM ticket t WHERE t.{status_col} IS NOT NULL ORDER BY 1"
            )
            status_options = [row[0] for row in cursor.fetchall()]
        ticket_status_value = ticket.get(status_col)
        if ticket_status_value and ticket_status_value not in status_options:
            status_options.append(ticket_status_value)
        if not status_options:
            status_options = ['Valid', 'Tidak Valid']

    if request.method == 'POST':
        seat_id = request.POST.get('seat') or None
        status_value = request.POST.get('status') if status_col else None

        with connection.cursor() as cursor:
            if status_col and status_value is not None:
                cursor.execute(
                    f"UPDATE ticket SET {status_col} = %s WHERE ticket_id = %s",
                    [status_value, pk]
                )
            # Update has_relationship
            cursor.execute("DELETE FROM has_relationship WHERE ticket_id = %s", [pk])
            if seat_id:
                cursor.execute(
                    "INSERT INTO has_relationship (ticket_id, seat_id) VALUES (%s, %s)",
                    [pk, seat_id]
                )

        messages.success(request, 'Tiket berhasil diperbarui.')
        return redirect('ticket_list')

    return render(request, 'tickets/ticket_form.html', {
        'ticket': ticket,
        'seats': seats,
        'status_options': status_options,
        'status_col': status_col,
        'ticket_status_value': ticket_status_value,
        'action': 'update',
    })


@raw_sql_login_required
def ticket_delete_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat menghapus tiket.')
        return redirect('ticket_list')

    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM ticket WHERE ticket_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        ticket_row = cursor.fetchone()
        if not ticket_row:
            messages.error(request, 'Tiket tidak ditemukan.')
            return redirect('ticket_list')
        ticket = dict(zip(cols, ticket_row))

    if request.method == 'POST':
        with connection.cursor() as cursor:
            # has_relationship akan ter-cascade delete jika ada ON DELETE CASCADE,
            # tapi untuk aman hapus manual dulu
            cursor.execute("DELETE FROM has_relationship WHERE ticket_id = %s", [pk])
            cursor.execute("DELETE FROM ticket WHERE ticket_id = %s", [pk])
        messages.success(request, 'Tiket berhasil dihapus.')
        return redirect('ticket_list')

    return render(request, 'tickets/ticket_confirm_delete.html', {'ticket': ticket})


# ============================================================
# TICKET CATEGORY VIEWS
# ============================================================

def ticket_category_list_view(request):
    query = request.GET.get('q', '').strip()
    event_filter = request.GET.get('event', '').strip()

    # FIX: kolom category_name (bukan name)
    sql = """
        SELECT tc.*, e.event_title AS event_title, v.venue_name AS venue_name
        FROM ticket_category tc
        LEFT JOIN event e ON tc.event_id = e.event_id
        LEFT JOIN venue v ON e.venue_id = v.venue_id
        WHERE 1=1
    """
    params = []

    scope_clause, scope_params = category_scope(request.user)
    sql += scope_clause
    params.extend(scope_params)

    if query:
        # FIX: category_name bukan name
        sql += " AND (LOWER(tc.category_name) LIKE LOWER(%s) OR LOWER(e.event_title) LIKE LOWER(%s))"
        params.extend([f"%{query}%", f"%{query}%"])

    if event_filter:
        sql += " AND tc.event_id = %s"
        params.append(event_filter)

    sql += " ORDER BY e.event_title ASC, tc.category_name ASC"

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        categories = [dict(zip(cols, row)) for row in cursor.fetchall()]

    events_sql = "SELECT * FROM event WHERE 1=1"
    events_params = []
    events_scope_clause, events_scope_params = event_scope(request.user)
    events_sql += events_scope_clause
    events_params.extend(events_scope_params)
    events_sql += " ORDER BY event_title"

    with connection.cursor() as cursor:
        cursor.execute(events_sql, events_params)
        cols = [col[0] for col in cursor.description]
        events = [dict(zip(cols, row)) for row in cursor.fetchall()]

    return render(request, 'tickets/category_list.html', {
        'categories': categories,
        'events': events,
        'query': query,
        'event_filter': event_filter,
        'can_manage': can_manage_category(request.user),
    })


@raw_sql_login_required
def ticket_category_create_view(request):
    if not can_manage_category(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk membuat kategori tiket.')
        return redirect('ticket_category_list')

    events_sql = "SELECT * FROM event WHERE 1=1"
    events_params = []
    events_scope_clause, events_scope_params = event_scope(request.user)
    events_sql += events_scope_clause
    events_params.extend(events_scope_params)
    events_sql += " ORDER BY event_title"

    with connection.cursor() as cursor:
        cursor.execute(events_sql, events_params)
        cols = [col[0] for col in cursor.description]
        events = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if request.method == 'POST':
        event_id = request.POST.get('event')
        # FIX: field name di form tetap "name" tapi kolom DB adalah category_name
        category_name = request.POST.get('name', '').strip()
        quota_raw = request.POST.get('quota', '')
        price_raw = request.POST.get('price', '')
        error = validate_category_input(event_id, category_name, quota_raw, price_raw, events)
        if error:
            messages.error(request, error)
        else:
            quota = int(quota_raw)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT v.capacity FROM event e LEFT JOIN venue v ON e.venue_id = v.venue_id WHERE e.event_id = %s",
                    [event_id]
                )
                capacity_row = cursor.fetchone()
                venue_capacity = capacity_row[0] if capacity_row else None

                if venue_capacity:
                    cursor.execute(
                        "SELECT COALESCE(SUM(quota), 0) FROM ticket_category WHERE event_id = %s",
                        [event_id]
                    )
                    total_quota = cursor.fetchone()[0]
                    if total_quota + quota > venue_capacity:
                        messages.error(request, 'Total kuota kategori tiket tidak boleh melebihi kapasitas venue.')
                        return render(request, 'tickets/category_form.html', {'events': events, 'action': 'create'})

                # FIX: kolom category_name (bukan name)
                cursor.execute(
                    "INSERT INTO ticket_category (event_id, category_name, quota, price) VALUES (%s, %s, %s, %s)",
                    [event_id, category_name, quota, price_raw]
                )

            messages.success(request, 'Kategori tiket berhasil dibuat.')
            return redirect('ticket_category_list')

    return render(request, 'tickets/category_form.html', {'events': events, 'action': 'create'})


@raw_sql_login_required
def ticket_category_update_view(request, pk):
    if not can_manage_category(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah kategori tiket.')
        return redirect('ticket_category_list')

    category_sql = """
        SELECT tc.* FROM ticket_category tc
        LEFT JOIN event e ON tc.event_id = e.event_id
        WHERE tc.category_id = %s
    """
    category_params = [pk]
    if request.user.role == 'organizer':
        category_sql += " AND e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)"
        category_params.append(str(request.user.id))

    with connection.cursor() as cursor:
        cursor.execute(category_sql, category_params)
        cols = [col[0] for col in cursor.description]
        category_row = cursor.fetchone()
        if not category_row:
            messages.error(request, 'Kategori tiket tidak ditemukan atau Anda tidak memiliki akses.')
            return redirect('ticket_category_list')
        category = dict(zip(cols, category_row))

    events_sql = "SELECT * FROM event WHERE 1=1"
    events_params = []
    events_scope_clause, events_scope_params = event_scope(request.user)
    events_sql += events_scope_clause
    events_params.extend(events_scope_params)
    events_sql += " ORDER BY event_title"

    with connection.cursor() as cursor:
        cursor.execute(events_sql, events_params)
        cols = [col[0] for col in cursor.description]
        events = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if request.method == 'POST':
        event_id = request.POST.get('event')
        category_name = request.POST.get('name', '').strip()
        quota_raw = request.POST.get('quota', '')
        price_raw = request.POST.get('price', '')
        error = validate_category_input(event_id, category_name, quota_raw, price_raw, events)
        if error:
            messages.error(request, error)
        else:
            quota = int(quota_raw)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT v.capacity FROM event e LEFT JOIN venue v ON e.venue_id = v.venue_id WHERE e.event_id = %s",
                    [event_id]
                )
                capacity_row = cursor.fetchone()
                venue_capacity = capacity_row[0] if capacity_row else None

                if venue_capacity:
                    cursor.execute(
                        "SELECT COALESCE(SUM(quota), 0) FROM ticket_category WHERE event_id = %s AND category_id != %s",
                        [event_id, pk]
                    )
                    total_quota = cursor.fetchone()[0]
                    if total_quota + quota > venue_capacity:
                        messages.error(request, 'Total kuota tidak boleh melebihi kapasitas venue.')
                        return render(request, 'tickets/category_form.html', {'events': events, 'category': category, 'action': 'update'})

                # FIX: kolom category_name
                cursor.execute(
                    "UPDATE ticket_category SET event_id = %s, category_name = %s, quota = %s, price = %s WHERE category_id = %s",
                    [event_id, category_name, quota, price_raw, pk]
                )

            messages.success(request, 'Kategori tiket berhasil diperbarui.')
            return redirect('ticket_category_list')

    return render(request, 'tickets/category_form.html', {'events': events, 'category': category, 'action': 'update'})


@raw_sql_login_required
def ticket_category_delete_view(request, pk):
    if not can_manage_category(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk menghapus kategori tiket.')
        return redirect('ticket_category_list')

    category_sql = """
        SELECT tc.* FROM ticket_category tc
        LEFT JOIN event e ON tc.event_id = e.event_id
        WHERE tc.category_id = %s
    """
    category_params = [pk]
    if request.user.role == 'organizer':
        category_sql += " AND e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)"
        category_params.append(str(request.user.id))

    with connection.cursor() as cursor:
        cursor.execute(category_sql, category_params)
        cols = [col[0] for col in cursor.description]
        category_row = cursor.fetchone()
        if not category_row:
            messages.error(request, 'Kategori tiket tidak ditemukan atau Anda tidak memiliki akses.')
            return redirect('ticket_category_list')
        category = dict(zip(cols, category_row))

    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM ticket_category WHERE category_id = %s", [pk])
        messages.success(request, 'Kategori tiket berhasil dihapus.')
        return redirect('ticket_category_list')

    return render(request, 'tickets/category_confirm_delete.html', {'category': category})


def validate_category_input(event_id, name, quota_raw, price_raw, events):
    if not all([event_id, name, quota_raw, price_raw]):
        return 'Semua field wajib diisi.'

    # FIX: key event pakai event_id (bukan id)
    event_exists = any(str(e.get('event_id')) == str(event_id) for e in events)
    if not event_exists:
        return 'Event tidak valid untuk role Anda.'

    try:
        quota = int(quota_raw)
        price = float(price_raw)
    except ValueError:
        return 'Quota dan price harus berupa angka.'

    if quota <= 0:
        return 'Quota harus berupa bilangan positif.'
    if price < 0:
        return 'Price tidak boleh negatif.'
    return None