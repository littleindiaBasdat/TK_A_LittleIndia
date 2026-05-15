from decimal import Decimal
import json
import uuid
from django.contrib import messages
from accounts.middleware import raw_sql_login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.db import connection, transaction


def _fmt_currency(amount):
    amount = float(amount)
    if amount >= 1_000_000:
        m = amount / 1_000_000
        return f"Rp {m:.1f}M" if m != int(m) else f"Rp {int(m)}M"
    elif amount >= 1_000:
        return f"Rp {int(amount):,}".replace(",", ".")
    return f"Rp {int(amount)}"


def _pg_error_message(exc):
    """Extract the primary message from a PostgreSQL trigger RAISE EXCEPTION."""
    cause = getattr(exc, '__cause__', None)
    if cause is not None:
        diag = getattr(cause, 'diag', None)
        if diag is not None and diag.message_primary:
            return diag.message_primary
    return str(exc).strip()


def apply_discount(subtotal, promotion_data):
    if not promotion_data:
        return subtotal
    discount_type = promotion_data.get('discount_type')
    discount_value = Decimal(str(promotion_data.get('discount_value', 0)))
    if discount_type == 'PERCENTAGE':
        discount = subtotal * discount_value / Decimal('100')
    else:
        discount = discount_value
    total = subtotal - discount
    return total if total > 0 else Decimal('0')


def dict_from_cursor(cursor):
    cols = [col[0] for col in cursor.description]
    return lambda row: dict(zip(cols, row))


@raw_sql_login_required
def order_list_view(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    user_id = request.user.id
    user_role = request.user.role
    
    # Build SQL based on role
    sql = """
        SELECT DISTINCT o.*,
               c.full_name as customer_name,
               e.event_title as event_name
        FROM "ORDER" o
        LEFT JOIN customer c ON o.customer_id = c.customer_id
        LEFT JOIN ticket t ON o.order_id = t.order_id
        LEFT JOIN ticket_category tc ON t.category_id = tc.category_id
        LEFT JOIN event e ON tc.event_id = e.event_id
        WHERE 1=1
    """
    params = []
    
    # Role-based filtering
    if user_role == 'customer':
        # Get customer_id from user_id
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT customer_id FROM customer WHERE user_id = %s",
                [user_id]
            )
            customer_row = cursor.fetchone()
            if customer_row:
                customer_id = customer_row[0]
                sql += " AND o.customer_id = %s"
                params.append(customer_id)
    elif user_role == 'organizer':
        # For organizer, filter by orders that have tickets in their events
        sql += """ AND o.order_id IN (
            SELECT DISTINCT t.order_id FROM ticket t
            JOIN ticket_category tc ON t.category_id = tc.category_id
            WHERE tc.event_id IN (
                SELECT e.event_id FROM event e 
                WHERE e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)
            )
        )"""
        params.append(user_id)
    
    # Query and status filters
    if query:
        sql += " AND (LOWER(c.full_name) LIKE LOWER(%s) OR o.order_id::text = %s)"
        params.extend([f"%{query}%", query])
    
    if status_filter:
        sql += " AND o.payment_status = %s"
        params.append(status_filter)
    
    sql += " ORDER BY o.order_date DESC"
    
    # Fetch orders
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        orders = [dict(zip(cols, row)) for row in cursor.fetchall()]
    
    # Get statistics
    stat_sql = """
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN payment_status = 'Lunas' THEN 1 ELSE 0 END) as paid_count,
            SUM(CASE WHEN payment_status = 'Pending' THEN 1 ELSE 0 END) as pending_count,
            COALESCE(SUM(CASE WHEN payment_status = 'Lunas' THEN total_amount ELSE 0 END), 0) as revenue
        FROM "ORDER" o
        WHERE 1=1
    """
    stat_params = []
    
    if user_role == 'customer':
        # Get customer_id from user_id for stats
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT customer_id FROM customer WHERE user_id = %s",
                [user_id]
            )
            customer_row = cursor.fetchone()
            if customer_row:
                customer_id = customer_row[0]
                stat_sql += " AND o.customer_id = %s"
                stat_params.append(customer_id)
    elif user_role == 'organizer':
        stat_sql += """ AND o.order_id IN (
            SELECT DISTINCT t.order_id FROM ticket t
            JOIN ticket_category tc ON t.category_id = tc.category_id
            WHERE tc.event_id IN (
                SELECT e.event_id FROM event e 
                WHERE e.organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)
            )
        )"""
        stat_params.append(user_id)
    
    with connection.cursor() as cursor:
        cursor.execute(stat_sql, stat_params)
        stats = dict(zip([col[0] for col in cursor.description], cursor.fetchone()))
    
    raw_revenue = stats.get('revenue', Decimal('0'))
    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'query': query,
        'status_filter': status_filter,
        'total_orders': stats.get('total_orders', 0),
        'paid_count': stats.get('paid_count', 0),
        'pending_count': stats.get('pending_count', 0),
        'revenue': _fmt_currency(raw_revenue),
        'show_revenue': request.user.role in ['admin', 'organizer'],
        'can_create': request.user.role == 'customer',
        'can_admin': request.user.role == 'admin',
    })


@raw_sql_login_required
def order_create_view(request):
    if request.user.role != 'customer':
        messages.error(request, 'Hanya customer yang dapat membuat order.')
        return redirect('order_list')

    selected_event_id = request.GET.get('event', '').strip()
    selected_event = None
    categories = []
    seats = []
    has_reserved_seating = False
    event_artists = []

    if selected_event_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT e.event_id, e.event_title, e.event_datetime,
                          v.venue_id, v.venue_name, v.city,
                          COALESCE(v.has_reserved_seating, FALSE)
                   FROM event e
                   LEFT JOIN venue v ON e.venue_id = v.venue_id
                   WHERE e.event_id = %s""",
                [selected_event_id]
            )
            row = cursor.fetchone()
            if row:
                selected_event = dict(zip(
                    ['event_id', 'event_title', 'event_datetime',
                     'venue_id', 'venue_name', 'city', 'has_reserved_seating'], row
                ))
                has_reserved_seating = bool(selected_event['has_reserved_seating'])

        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT category_id, category_name, price, quota
                   FROM ticket_category WHERE event_id = %s ORDER BY price DESC""",
                [selected_event_id]
            )
            categories = [dict(zip(['category_id', 'category_name', 'price', 'quota'], r))
                          for r in cursor.fetchall()]

        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.name FROM event_artist ea
                   JOIN artist a ON ea.artist_id = a.artist_id
                   WHERE ea.event_id = %s ORDER BY a.name""",
                [selected_event_id]
            )
            event_artists = [r[0] for r in cursor.fetchall()]

        if has_reserved_seating and selected_event:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT s.seat_id, s.section, s.row_number, s.seat_number
                       FROM seat s
                       WHERE s.venue_id = %s
                         AND s.seat_id NOT IN (SELECT DISTINCT seat_id FROM has_relationship)
                       ORDER BY s.section, s.row_number, s.seat_number""",
                    [selected_event['venue_id']]
                )
                seats = [dict(zip(['seat_id', 'section', 'row_number', 'seat_number'], r))
                         for r in cursor.fetchall()]

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT promotion_id, promo_code, discount_type, discount_value,
                      start_date, end_date, usage_limit,
                      (SELECT COUNT(*) FROM order_promotion op WHERE op.promotion_id = p.promotion_id) AS usage_count
               FROM promotion p
               WHERE start_date <= CURRENT_DATE AND end_date >= CURRENT_DATE
               ORDER BY promo_code"""
        )
        cols = [col[0] for col in cursor.description]
        promotions_raw = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Serialize promos for client-side validation
    promotions_json = json.dumps([
        {
            'code': p['promo_code'],
            'type': p['discount_type'],
            'value': float(p['discount_value']),
            'limit': p['usage_limit'],
            'used': int(p['usage_count']),
        }
        for p in promotions_raw
    ])

    def _render_create(extra=None):
        ctx = {
            'selected_event': selected_event,
            'categories': categories,
            'seats': seats,
            'promotions_json': promotions_json,
            'has_reserved_seating': has_reserved_seating,
            'event_artists': event_artists,
            'action': 'create',
        }
        if extra:
            ctx.update(extra)
        return render(request, 'orders/order_form.html', ctx)

    if request.method == 'POST':
        category_id = request.POST.get('category', '').strip()
        quantity_raw = request.POST.get('quantity', '1').strip()
        promo_code = request.POST.get('promo_code', '').strip()
        seat_id = request.POST.get('seat') or None

        if not category_id:
            messages.error(request, 'Kategori tiket wajib dipilih.')
            return _render_create()
        if not quantity_raw.isdigit():
            messages.error(request, 'Jumlah tiket tidak valid.')
            return _render_create()

        quantity = int(quantity_raw)
        if quantity < 1 or quantity > 10:
            messages.error(request, 'Jumlah tiket harus 1 sampai 10.')
            return _render_create()

        with connection.cursor() as cursor:
            cursor.execute("SELECT price FROM ticket_category WHERE category_id = %s", [category_id])
            cat_row = cursor.fetchone()
            if not cat_row:
                messages.error(request, 'Kategori tiket tidak ditemukan.')
                return _render_create()
            price = cat_row[0]

        promotion_id = None
        promo_data = None
        if promo_code:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT promotion_id, discount_type, discount_value FROM promotion WHERE LOWER(promo_code) = LOWER(%s)",
                    [promo_code]
                )
                promo_row = cursor.fetchone()
                if not promo_row:
                    messages.error(request, f'Kode promo "{promo_code}" tidak ditemukan.')
                    return _render_create()
                promotion_id = promo_row[0]
                promo_data = {'discount_type': promo_row[1], 'discount_value': promo_row[2]}

        subtotal = Decimal(str(price)) * quantity
        total = apply_discount(subtotal, promo_data)

        with connection.cursor() as cursor:
            cursor.execute("SELECT customer_id FROM customer WHERE user_id = %s", [request.user.id])
            cust_row = cursor.fetchone()
            if not cust_row:
                messages.error(request, 'Data customer tidak ditemukan.')
                return _render_create()
            customer_id = cust_row[0]

        order_id = str(uuid.uuid4())
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO "ORDER" (order_id, customer_id, total_amount, payment_status, order_date)
                           VALUES (%s, %s, %s, %s, %s)""",
                        [order_id, customer_id, total, 'Pending', timezone.now()]
                    )
                    first_ticket_id = None
                    for _ in range(quantity):
                        ticket_id = str(uuid.uuid4())
                        ticket_code = f'TKT-{uuid.uuid4().hex[:10].upper()}'
                        cursor.execute(
                            """INSERT INTO ticket (ticket_id, ticket_code, category_id, order_id)
                               VALUES (%s, %s, %s, %s)""",
                            [ticket_id, ticket_code, category_id, order_id]
                        )
                        if first_ticket_id is None:
                            first_ticket_id = ticket_id

                    if seat_id and first_ticket_id:
                        cursor.execute(
                            "INSERT INTO has_relationship (ticket_id, seat_id) VALUES (%s, %s)",
                            [first_ticket_id, seat_id]
                        )
                    if promotion_id:
                        cursor.execute(
                            "INSERT INTO order_promotion (order_id, promotion_id) VALUES (%s, %s)",
                            [order_id, promotion_id]
                        )
        except Exception as exc:
            messages.error(request, _pg_error_message(exc))
            return _render_create()

        messages.success(request, f'Pesanan berhasil! {quantity} tiket telah dipesan.')
        return redirect('order_list')

    return _render_create()


@raw_sql_login_required
def order_update_view(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat mengubah order.')
        return redirect('order_list')
    
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT DISTINCT o.*, c.full_name AS customer_name, e.event_title AS event_name
               FROM "ORDER" o
               LEFT JOIN customer c ON o.customer_id = c.customer_id
               LEFT JOIN ticket t ON o.order_id = t.order_id
               LEFT JOIN ticket_category tc ON t.category_id = tc.category_id
               LEFT JOIN event e ON tc.event_id = e.event_id
               WHERE o.order_id = %s""",
            [pk]
        )
        cols = [col[0] for col in cursor.description]
        order_row = cursor.fetchone()
        if not order_row:
            messages.error(request, 'Order tidak ditemukan.')
            return redirect('order_list')
        order = dict(zip(cols, order_row))

    if request.method == 'POST':
        payment_status = request.POST.get('payment_status', 'Pending')
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE \"ORDER\" SET payment_status = %s WHERE order_id = %s",
                    [payment_status, pk]
                )
        except Exception as exc:
            messages.error(request, str(exc))
            return render(request, 'orders/order_form.html', {'order': order, 'action': 'update'})

        messages.success(request, 'Order berhasil diperbarui.')
        return redirect('order_list')

    return render(request, 'orders/order_form.html', {'order': order, 'action': 'update'})


@raw_sql_login_required
def order_delete_view(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat menghapus order.')
        return redirect('order_list')
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM \"ORDER\" WHERE order_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        order_row = cursor.fetchone()
        if not order_row:
            messages.error(request, 'Order tidak ditemukan.')
            return redirect('order_list')
        order = dict(zip(cols, order_row))
    
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM \"ORDER\" WHERE order_id = %s", [pk])
        messages.success(request, 'Order berhasil dihapus.')
        return redirect('order_list')
    
    return render(request, 'orders/order_confirm_delete.html', {'order': order})
