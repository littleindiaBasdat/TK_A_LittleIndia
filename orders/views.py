from decimal import Decimal
import uuid
from django.contrib import messages
from accounts.middleware import raw_sql_login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.db import connection
from .models import Order


def apply_discount(subtotal, promotion_data):
    if not promotion_data:
        return subtotal
    discount_type = promotion_data.get('discount_type')
    discount_value = Decimal(str(promotion_data.get('discount_value', 0)))
    if discount_type == 'percent':
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
    
    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'query': query,
        'status_filter': status_filter,
        'total_orders': stats.get('total_orders', 0),
        'paid_count': stats.get('paid_count', 0),
        'pending_count': stats.get('pending_count', 0),
        'revenue': stats.get('revenue', Decimal('0')),
        'can_create': request.user.role == 'customer',
        'can_admin': request.user.role == 'admin',
    })


@raw_sql_login_required
@raw_sql_login_required
def order_create_view(request):
    if request.user.role != 'customer':
        messages.error(request, 'Hanya customer yang dapat membuat order.')
        return redirect('order_list')
    
    # Fetch categories dengan join event untuk display
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT tc.category_id, tc.category_name, tc.quota, tc.price, tc.event_id,
                   e.event_title, e.event_datetime, v.venue_name
            FROM ticket_category tc
            JOIN event e ON tc.event_id = e.event_id
            LEFT JOIN venue v ON e.venue_id = v.venue_id
            ORDER BY e.event_datetime DESC, tc.category_name
        """)
        cols = [col[0] for col in cursor.description]
        categories = [dict(zip(cols, row)) for row in cursor.fetchall()]
    
    # Fetch promotions
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM promotion ORDER BY promo_code")
        cols = [col[0] for col in cursor.description]
        promotions = [dict(zip(cols, row)) for row in cursor.fetchall()]
    
    if request.method == 'POST':
        category_id = request.POST.get('category')
        quantity_raw = request.POST.get('quantity', '1')
        promo_code = request.POST.get('promo_code', '').strip()
        
        if not category_id or not quantity_raw.isdigit():
            messages.error(request, 'Kategori tiket dan jumlah tiket wajib diisi dengan benar.')
        else:
            quantity = int(quantity_raw)
            if quantity < 1 or quantity > 10:
                messages.error(request, 'Jumlah tiket harus 1 sampai 10.')
            else:
                # Fetch category
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM ticket_category WHERE category_id = %s", [category_id])
                    cols = [col[0] for col in cursor.description]
                    category_row = cursor.fetchone()
                    if not category_row:
                        messages.error(request, 'Kategori tiket tidak ditemukan.')
                        return render(request, 'orders/order_form.html', {'categories': categories, 'promotions': promotions})
                    category = dict(zip(cols, category_row))
                
                promotion = None
                promotion_id = None
                if promo_code:
                    today = timezone.localdate()
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """SELECT p.*,
                                      (SELECT COUNT(*) FROM order_promotion op WHERE op.promotion_id = p.promotion_id) AS usage_count
                               FROM promotion p
                               WHERE LOWER(p.promo_code) = LOWER(%s)
                               AND p.start_date <= %s
                               AND p.end_date >= %s
                               AND (SELECT COUNT(*) FROM order_promotion op WHERE op.promotion_id = p.promotion_id) < p.usage_limit""",
                            [promo_code, today, today]
                        )
                        cols = [col[0] for col in cursor.description]
                        promo_row = cursor.fetchone()
                        if not promo_row:
                            messages.error(request, 'Kode promo tidak valid atau sudah tidak tersedia.')
                            return render(request, 'orders/order_form.html', {'categories': categories, 'promotions': promotions})
                        promotion = dict(zip(cols, promo_row))
                        promotion_id = promotion['promotion_id']  # Fixed: promotion_id not id
                
                subtotal = Decimal(str(category['price'])) * quantity
                total = apply_discount(subtotal, promotion)
                
                # Create order (only with valid columns)
                order_id = str(uuid.uuid4())
                with connection.cursor() as cursor:
                    # Get customer_id from user_id
                    cursor.execute(
                        "SELECT customer_id FROM customer WHERE user_id = %s",
                        [request.user.id]
                    )
                    customer_row = cursor.fetchone()
                    if not customer_row:
                        messages.error(request, 'Data customer tidak ditemukan.')
                        return render(request, 'orders/order_form.html', {'categories': categories, 'promotions': promotions})
                    customer_id = customer_row[0]
                    
                    cursor.execute(
                        """INSERT INTO "ORDER" (order_id, customer_id, total_amount, payment_status, order_date)
                           VALUES (%s, %s, %s, %s, %s)""",
                        [order_id, customer_id, total, 'Pending', timezone.now()]
                    )
                    
                    # Link promotion if applied
                    if promotion_id:
                        op_id = str(uuid.uuid4())
                        cursor.execute(
                            "INSERT INTO order_promotion (order_promotion_id, order_id, promotion_id) VALUES (%s, %s, %s)",
                            [op_id, order_id, promotion_id]
                        )
                
                messages.success(request, f'Order {order_id} berhasil dibuat.')
                return redirect('order_list')
    
    return render(request, 'orders/order_form.html', {'categories': categories, 'promotions': promotions})


@raw_sql_login_required
def order_update_view(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat mengubah order.')
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
        payment_status = request.POST.get('payment_status', 'pending')
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE \"ORDER\" SET payment_status = %s WHERE order_id = %s",
                [payment_status, pk]
            )
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
