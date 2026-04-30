import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from orders.models import Order
from seats.models import Seat
from .models import Ticket, TicketCategory


def can_create(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


def can_admin(user):
    return user.is_authenticated and user.role == 'admin'


def scoped_tickets(user):
    tickets = Ticket.objects.select_related('order__customer', 'order__event__venue', 'category', 'seat').all()
    if user.role == 'customer':
        return tickets.filter(order__customer=user)
    if user.role == 'organizer':
        return tickets.filter(order__event__organizer=user)
    return tickets


@login_required
def ticket_list_view(request):
    tickets = scoped_tickets(request.user)
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    if query:
        tickets = tickets.filter(Q(code__icontains=query) | Q(order__event__title__icontains=query))
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    title = 'Tiket Saya' if request.user.role == 'customer' else 'Manajemen Tiket'
    return render(request, 'tickets/ticket_list.html', {
        'tickets': tickets,
        'query': query,
        'status_filter': status_filter,
        'title': title,
        'can_create': can_create(request.user),
        'can_admin': can_admin(request.user),
    })


@login_required
def ticket_create_view(request):
    if not can_create(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk membuat tiket.')
        return redirect('ticket_list')
    orders = Order.objects.select_related('customer', 'event__venue').all()
    if request.user.role == 'organizer':
        orders = orders.filter(event__organizer=request.user)
    categories = TicketCategory.objects.select_related('event').all()
    seats = Seat.objects.select_related('venue').filter(ticket__isnull=True)
    if request.method == 'POST':
        order_id = request.POST.get('order')
        category_id = request.POST.get('category')
        seat_id = request.POST.get('seat')
        if not all([order_id, category_id]):
            messages.error(request, 'Order dan kategori tiket wajib dipilih.')
        else:
            order = get_object_or_404(orders, pk=order_id)
            category = get_object_or_404(categories, pk=category_id, event=order.event)
            seat = None
            if seat_id:
                seat = get_object_or_404(seats, pk=seat_id, venue=order.event.venue)
            code = f'TKT-{uuid.uuid4().hex[:10].upper()}'
            Ticket.objects.create(order=order, category=category, seat=seat, code=code)
            messages.success(request, 'Tiket berhasil dibuat.')
            return redirect('ticket_list')
    return render(request, 'tickets/ticket_form.html', {
        'orders': orders,
        'categories': categories,
        'seats': seats,
        'action': 'create',
    })


@login_required
def ticket_update_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat mengubah tiket.')
        return redirect('ticket_list')
    ticket = get_object_or_404(Ticket.objects.select_related('order__event__venue', 'seat'), pk=pk)
    seats = Seat.objects.select_related('venue').filter(Q(ticket__isnull=True) | Q(pk=ticket.seat_id), venue=ticket.order.event.venue)
    if request.method == 'POST':
        ticket.status = request.POST.get('status', ticket.status)
        seat_id = request.POST.get('seat')
        ticket.seat = get_object_or_404(seats, pk=seat_id) if seat_id else None
        ticket.save()
        messages.success(request, 'Tiket berhasil diperbarui.')
        return redirect('ticket_list')
    return render(request, 'tickets/ticket_form.html', {
        'ticket': ticket,
        'seats': seats,
        'action': 'update',
    })


@login_required
def ticket_delete_view(request, pk):
    if not can_admin(request.user):
        messages.error(request, 'Hanya admin yang dapat menghapus tiket.')
        return redirect('ticket_list')
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        ticket.delete()
        messages.success(request, 'Tiket berhasil dihapus.')
        return redirect('ticket_list')
    return render(request, 'tickets/ticket_confirm_delete.html', {'ticket': ticket})
