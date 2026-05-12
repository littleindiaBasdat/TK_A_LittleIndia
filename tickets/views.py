import uuid
from django.contrib import messages
from accounts.middleware import raw_sql_login_required
from django.shortcuts import redirect, render
from django.db import connection


def can_create(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


def can_admin(user):
    return user.is_authenticated and user.role == 'admin'


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
        return " AND e.organizer_id = %s", [user_id]
    return "", []


def category_scope(user):
    """Returns SQL WHERE clause and params for category scoping"""
    user_id = str(user.id)
    user_role = user.role

    if user_role == 'organizer':
        return " AND e.organizer_id = %s", [user_id]
    return "", []


def event_scope(user):
    """Returns SQL WHERE clause and params for event scoping"""
    user_id = str(user.id)
    user_role = user.role

    if user_role == 'organizer':
        return " AND organizer_id = %s", [user_id]
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

    # FIX: kolom di DB:
    #   ticket       -> ticket_id, ticket_code, category_id, order_id  (TIDAK ada status, seat_id)
    #   ticket_category -> category_id, category_name, quota, price, event_id
    #   event        -> event_id, event_title, venue_id, organizer_id
    #   customer     -> customer_id, full_name, user_id
    #   "ORDER"      -> order_id, order_date, payment_status, total_amount, customer_id
    #   has_relationship -> ticket_id, seat_id  (relasi ticket <-> seat)
    #   seat         -> seat_id, section, row_number, seat_number, venue_id
    sql = """
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
            v.venue_name,
            hr.seat_id,
            s.section          AS seat_section,
            s.row_number       AS seat_row,
            s.seat_number      AS seat_number
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

    # FIX: ticket tidak punya kolom status — filter status dihapus
    # (jika nanti ada kolom status di schema, baru bisa diaktifkan)

    # Fetch tickets
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        tickets = [dict(zip(cols, row)) for row in cursor.fetchall()]

    title = 'Tiket Saya' if request.user.role == 'customer' else 'Manajemen Tiket'
    return render(request, 'tickets/ticket_list.html', {
        'tickets': tickets,
        'query': query,
        'status_filter': status_filter,
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
    orders_sql = """
        SELECT DISTINCT o.order_id, o.order_date, o.payment_status, o.total_amount,
               c.full_name AS customer_name,
               e.event_id, e.event_title
        FROM "ORDER" o
        LEFT JOIN customer c ON o.customer_id = c.customer_id
        LEFT JOIN ticket t ON o.order_id = t.order_id
        LEFT JOIN ticket_category tc ON t.category_id = tc.category_id
        LEFT JOIN event e ON tc.event_id = e.event_id
        ORDER BY o.order_date DESC
    """
    orders_params = []

    with connection.cursor() as cursor:
        cursor.execute(orders_sql, orders_params)
        cols = [col[0] for col in cursor.description]
        orders = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Get categories with quota usage info
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
        categories_sql += " AND e.organizer_id = %s"
        categories_params.append(str(request.user.id))
    
    categories_sql += " GROUP BY tc.category_id, tc.category_name, tc.quota, tc.price, tc.event_id, e.event_title, v.venue_name, v.venue_id"

    with connection.cursor() as cursor:
        cursor.execute(categories_sql, categories_params)
        cols = [col[0] for col in cursor.description]
        categories = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Get available seats (not assigned to any ticket)
    seats_sql = """
        SELECT s.*, v.venue_name AS venue_name
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
            with connection.cursor() as cursor:
                # Verify order exists
                cursor.execute('SELECT order_id FROM "ORDER" WHERE order_id = %s', [order_id])
                if not cursor.fetchone():
                    messages.error(request, 'Order tidak ditemukan.')
                    return render(request, 'tickets/ticket_form.html', {
                        'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                    })

                # Verify category exists
                cursor.execute("SELECT category_id FROM ticket_category WHERE category_id = %s", [category_id])
                if not cursor.fetchone():
                    messages.error(request, 'Kategori tiket tidak valid.')
                    return render(request, 'tickets/ticket_form.html', {
                        'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                    })

                # Verify seat if provided
                if seat_id:
                    cursor.execute("SELECT seat_id FROM seat WHERE seat_id = %s", [seat_id])
                    if not cursor.fetchone():
                        messages.error(request, 'Seat tidak valid.')
                        return render(request, 'tickets/ticket_form.html', {
                            'orders': orders, 'categories': categories, 'seats': seats, 'action': 'create',
                        })

                # FIX: INSERT sesuai kolom DB: ticket_id, ticket_code, category_id, order_id
                ticket_id = str(uuid.uuid4())
                code = f'TKT-{uuid.uuid4().hex[:10].upper()}'
                cursor.execute(
                    """INSERT INTO ticket (ticket_id, ticket_code, category_id, order_id)
                       VALUES (%s, %s, %s, %s)""",
                    [ticket_id, code, category_id, order_id]
                )

                # Insert seat relation if seat provided
                if seat_id:
                    cursor.execute(
                        "INSERT INTO has_relationship (ticket_id, seat_id) VALUES (%s, %s)",
                        [ticket_id, seat_id]
                    )

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

    if request.method == 'POST':
        seat_id = request.POST.get('seat') or None

        with connection.cursor() as cursor:
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

@raw_sql_login_required
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
        category_sql += " AND e.organizer_id = %s"
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
        category_sql += " AND e.organizer_id = %s"
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