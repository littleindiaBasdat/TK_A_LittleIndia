import uuid
from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import connection


def can_admin(user):
    return user.is_authenticated and user.role == 'admin'


def promotion_list_view(request):
    query = request.GET.get('q', '').strip()
    discount_filter = request.GET.get('type', '').strip()
    
    # Build SQL query
    sql = """SELECT p.*,
                    (SELECT COUNT(*) FROM order_promotion op WHERE op.promotion_id = p.promotion_id) AS usage_count
             FROM promotion p WHERE 1=1"""
    params = []
    
    if query:
        sql += " AND promo_code ILIKE %s"
        params.append(f"%{query}%")
    
    if discount_filter:
        sql += " AND discount_type = %s"
        params.append(discount_filter)
    
    # Fetch promotions
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        promotions = [dict(zip(cols, row)) for row in cursor.fetchall()]
    
    # Calculate statistics
    total_usage = 0
    percent_count = 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM order_promotion")
        total_usage = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM promotion WHERE discount_type = 'percent'")
        percent_count = cursor.fetchone()[0]
    
    return render(request, 'promotions/promotion_list.html', {
        'promotions': promotions,
        'query': query,
        'discount_filter': discount_filter,
        'total_promos': len(promotions),
        'total_usage': total_usage,
        'percent_count': percent_count,
        'can_admin': can_admin(request.user),
    })


def promotion_create_view(request):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat membuat promosi.')
        return redirect('promotion_list')
    if request.method == 'POST':
        promo_code = request.POST.get('promo_code', '').strip().upper()
        discount_type = request.POST.get('discount_type', '')
        discount_value = request.POST.get('discount_value', '')
        start_date = request.POST.get('start_date', '')
        end_date = request.POST.get('end_date', '')
        usage_limit = request.POST.get('usage_limit', '')
        error = validate_promotion(promo_code, discount_type, discount_value, start_date, end_date, usage_limit)
        if error:
            messages.error(request, error)
        else:
            # Check if promo code already exists
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM promotion WHERE LOWER(promo_code) = LOWER(%s)",
                    [promo_code]
                )
                if cursor.fetchone():
                    messages.error(request, 'Kode promo sudah digunakan.')
                    return render(request, 'promotions/promotion_form.html', {'action': 'create'})
            
            # Create promotion
            with connection.cursor() as cursor:
                promo_id = str(uuid.uuid4())
                cursor.execute(
                    """INSERT INTO promotion (promotion_id, promo_code, discount_type, discount_value, start_date, end_date, usage_limit)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    [promo_id, promo_code, discount_type, discount_value, start_date, end_date, usage_limit]
                )
            messages.success(request, 'Promosi berhasil dibuat.')
            return redirect('promotion_list')
    return render(request, 'promotions/promotion_form.html', {'action': 'create'})


def promotion_update_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat mengubah promosi.')
        return redirect('promotion_list')
    
    # Fetch promotion
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM promotion WHERE promotion_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        promo_row = cursor.fetchone()
        if not promo_row:
            messages.error(request, 'Promosi tidak ditemukan.')
            return redirect('promotion_list')
        promotion = dict(zip(cols, promo_row))
    
    if request.method == 'POST':
        promo_code = request.POST.get('promo_code', '').strip().upper()
        discount_type = request.POST.get('discount_type', '')
        discount_value = request.POST.get('discount_value', '')
        start_date = request.POST.get('start_date', '')
        end_date = request.POST.get('end_date', '')
        usage_limit = request.POST.get('usage_limit', '')
        error = validate_promotion(promo_code, discount_type, discount_value, start_date, end_date, usage_limit)
        if error:
            messages.error(request, error)
        else:
            # Check if promo code already exists (excluding current)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM promotion WHERE LOWER(promo_code) = LOWER(%s) AND promotion_id != %s",
                    [promo_code, pk]
                )
                if cursor.fetchone():
                    messages.error(request, 'Kode promo sudah digunakan.')
                    return render(request, 'promotions/promotion_form.html', {'promotion': promotion, 'action': 'update'})
            
            # Update promotion
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE promotion SET promo_code = %s, discount_type = %s, discount_value = %s, 
                       start_date = %s, end_date = %s, usage_limit = %s WHERE promotion_id = %s""",
                    [promo_code, discount_type, discount_value, start_date, end_date, usage_limit, pk]
                )
            messages.success(request, 'Promosi berhasil diperbarui.')
            return redirect('promotion_list')
    
    return render(request, 'promotions/promotion_form.html', {'promotion': promotion, 'action': 'update'})


def promotion_delete_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat menghapus promosi.')
        return redirect('promotion_list')
    
    # Fetch promotion
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM promotion WHERE promotion_id = %s", [pk])
        cols = [col[0] for col in cursor.description]
        promo_row = cursor.fetchone()
        if not promo_row:
            messages.error(request, 'Promosi tidak ditemukan.')
            return redirect('promotion_list')
        promotion = dict(zip(cols, promo_row))
    
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM promotion WHERE promotion_id = %s", [pk])
        messages.success(request, 'Promosi berhasil dihapus.')
        return redirect('promotion_list')
    
    return render(request, 'promotions/promotion_confirm_delete.html', {'promotion': promotion})


def validate_promotion(promo_code, discount_type, discount_value, start_date, end_date, usage_limit):
    if not all([promo_code, discount_type, discount_value, start_date, end_date, usage_limit]):
        return 'Semua field wajib diisi.'
    if discount_type not in ['percent', 'nominal']:
        return 'Tipe diskon tidak valid.'
    try:
        value = float(discount_value)
        limit = int(usage_limit)
    except ValueError:
        return 'Nilai diskon dan batas penggunaan harus berupa angka.'
    if value <= 0:
        return 'Nilai diskon harus lebih dari 0.'
    if limit <= 0:
        return 'Batas penggunaan harus lebih dari 0.'
    if end_date < start_date:
        return 'Tanggal berakhir harus sama dengan atau setelah tanggal mulai.'
    return None
