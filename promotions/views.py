from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from .models import Promotion


def can_admin(user):
    return user.is_authenticated and user.role == 'admin'


def promotion_list_view(request):
    promotions = Promotion.objects.all()
    query = request.GET.get('q', '').strip()
    discount_filter = request.GET.get('type', '')
    if query:
        promotions = promotions.filter(promo_code__icontains=query)
    if discount_filter:
        promotions = promotions.filter(discount_type=discount_filter)
    total_usage = promotions.aggregate(total=Sum('usage_count'))['total'] or 0
    return render(request, 'promotions/promotion_list.html', {
        'promotions': promotions,
        'query': query,
        'discount_filter': discount_filter,
        'total_promos': promotions.count(),
        'total_usage': total_usage,
        'percent_count': promotions.filter(discount_type='percent').count(),
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
        elif Promotion.objects.filter(promo_code=promo_code).exists():
            messages.error(request, 'Kode promo sudah digunakan.')
        else:
            Promotion.objects.create(
                promo_code=promo_code,
                discount_type=discount_type,
                discount_value=discount_value,
                start_date=start_date,
                end_date=end_date,
                usage_limit=usage_limit,
            )
            messages.success(request, 'Promosi berhasil dibuat.')
            return redirect('promotion_list')
    return render(request, 'promotions/promotion_form.html', {'action': 'create'})


def promotion_update_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat mengubah promosi.')
        return redirect('promotion_list')
    promotion = get_object_or_404(Promotion, pk=pk)
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
        elif Promotion.objects.filter(promo_code=promo_code).exclude(pk=promotion.pk).exists():
            messages.error(request, 'Kode promo sudah digunakan.')
        else:
            promotion.promo_code = promo_code
            promotion.discount_type = discount_type
            promotion.discount_value = discount_value
            promotion.start_date = start_date
            promotion.end_date = end_date
            promotion.usage_limit = usage_limit
            promotion.save()
            messages.success(request, 'Promosi berhasil diperbarui.')
            return redirect('promotion_list')
    return render(request, 'promotions/promotion_form.html', {'promotion': promotion, 'action': 'update'})


def promotion_delete_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat menghapus promosi.')
        return redirect('promotion_list')
    promotion = get_object_or_404(Promotion, pk=pk)
    if request.method == 'POST':
        promotion.delete()
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
