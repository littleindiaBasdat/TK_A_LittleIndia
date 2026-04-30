from decimal import Decimal
import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from promotions.models import Promotion
from tickets.models import TicketCategory
from .models import Order


def scoped_orders(user):
    orders = Order.objects.select_related('customer', 'event__organizer', 'promotion').all()
    if user.role == 'customer':
        return orders.filter(customer=user)
    if user.role == 'organizer':
        return orders.filter(event__organizer=user)
    return orders


def apply_discount(subtotal, promotion):
    if not promotion:
        return subtotal
    if promotion.discount_type == 'percent':
        discount = subtotal * promotion.discount_value / Decimal('100')
    else:
        discount = promotion.discount_value
    total = subtotal - discount
    return total if total > 0 else Decimal('0')


@login_required
def order_list_view(request):
    orders = scoped_orders(request.user).order_by('-order_date')
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    if query:
        query_filter = Q(event__title__icontains=query) | Q(customer__full_name__icontains=query)
        try:
            query_filter |= Q(id=uuid.UUID(query))
        except ValueError:
            pass
        orders = orders.filter(query_filter)
    if status_filter:
        orders = orders.filter(payment_status=status_filter)
    paid_orders = orders.filter(payment_status='paid')
    pending_orders = orders.filter(payment_status='pending')
    revenue = paid_orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'query': query,
        'status_filter': status_filter,
        'total_orders': orders.count(),
        'paid_count': paid_orders.count(),
        'pending_count': pending_orders.count(),
        'revenue': revenue,
        'can_create': request.user.role == 'customer',
        'can_admin': request.user.role == 'admin',
    })


@login_required
def order_create_view(request):
    if request.user.role != 'customer':
        messages.error(request, 'Hanya customer yang dapat membuat order.')
        return redirect('order_list')
    categories = TicketCategory.objects.select_related('event__venue').all()
    promotions = Promotion.objects.all()
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
                category = get_object_or_404(categories, pk=category_id)
                promotion = None
                if promo_code:
                    today = timezone.localdate()
                    promotion = Promotion.objects.filter(
                        promo_code__iexact=promo_code,
                        start_date__lte=today,
                        end_date__gte=today,
                        usage_count__lt=F('usage_limit'),
                    ).first()
                    if not promotion:
                        messages.error(request, 'Kode promo tidak valid atau sudah tidak tersedia.')
                        return render(request, 'orders/order_form.html', {'categories': categories, 'promotions': promotions})
                subtotal = category.price * quantity
                total = apply_discount(subtotal, promotion)
                order = Order.objects.create(
                    customer=request.user,
                    event=category.event,
                    promotion=promotion,
                    total_amount=total,
                    payment_status='pending',
                )
                if promotion:
                    promotion.usage_count += 1
                    promotion.save()
                messages.success(request, f'Order {order.id} berhasil dibuat.')
                return redirect('order_list')
    return render(request, 'orders/order_form.html', {'categories': categories, 'promotions': promotions})


@login_required
def order_update_view(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat mengubah order.')
        return redirect('order_list')
    order = get_object_or_404(Order.objects.select_related('customer', 'event'), pk=pk)
    if request.method == 'POST':
        order.payment_status = request.POST.get('payment_status', order.payment_status)
        order.save()
        messages.success(request, 'Order berhasil diperbarui.')
        return redirect('order_list')
    return render(request, 'orders/order_form.html', {'order': order, 'action': 'update'})


@login_required
def order_delete_view(request, pk):
    if request.user.role != 'admin':
        messages.error(request, 'Hanya admin yang dapat menghapus order.')
        return redirect('order_list')
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.delete()
        messages.success(request, 'Order berhasil dihapus.')
        return redirect('order_list')
    return render(request, 'orders/order_confirm_delete.html', {'order': order})
