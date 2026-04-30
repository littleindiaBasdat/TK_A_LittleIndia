import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from events.models import Event
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


def category_scope(user):
    categories = TicketCategory.objects.select_related('event__venue', 'event__organizer').all()
    if user.is_authenticated and user.role == 'organizer':
        return categories.filter(event__organizer=user)
    return categories


def event_scope(user):
    events = Event.objects.select_related('venue', 'organizer').all().order_by('title')
    if user.is_authenticated and user.role == 'organizer':
        return events.filter(organizer=user)
    return events


def can_manage_category(user):
    return user.is_authenticated and user.role in ['admin', 'organizer']


def ticket_category_list_view(request):
    categories = category_scope(request.user)
    query = request.GET.get('q', '').strip()
    event_filter = request.GET.get('event', '')
    if query:
        categories = categories.filter(Q(name__icontains=query) | Q(event__title__icontains=query))
    if event_filter:
        categories = categories.filter(event_id=event_filter)
    return render(request, 'tickets/category_list.html', {
        'categories': categories,
        'events': event_scope(request.user),
        'query': query,
        'event_filter': event_filter,
        'can_manage': can_manage_category(request.user),
    })


@login_required
def ticket_category_create_view(request):
    if not can_manage_category(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk membuat kategori tiket.')
        return redirect('ticket_category_list')
    events = event_scope(request.user)
    if request.method == 'POST':
        event_id = request.POST.get('event')
        name = request.POST.get('name', '').strip()
        quota_raw = request.POST.get('quota', '')
        price_raw = request.POST.get('price', '')
        error = validate_category_input(event_id, name, quota_raw, price_raw, events)
        if error:
            messages.error(request, error)
        else:
            event = get_object_or_404(events, pk=event_id)
            quota = int(quota_raw)
            total_quota = TicketCategory.objects.filter(event=event).aggregate(total=Sum('quota'))['total'] or 0
            if event.venue and total_quota + quota > event.venue.capacity:
                messages.error(request, 'Total kuota kategori tiket tidak boleh melebihi kapasitas venue.')
            else:
                TicketCategory.objects.create(event=event, name=name, quota=quota, price=price_raw)
                messages.success(request, 'Kategori tiket berhasil dibuat.')
                return redirect('ticket_category_list')
    return render(request, 'tickets/category_form.html', {'events': events, 'action': 'create'})


@login_required
def ticket_category_update_view(request, pk):
    if not can_manage_category(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk mengubah kategori tiket.')
        return redirect('ticket_category_list')
    category = get_object_or_404(category_scope(request.user), pk=pk)
    events = event_scope(request.user)
    if request.method == 'POST':
        event_id = request.POST.get('event')
        name = request.POST.get('name', '').strip()
        quota_raw = request.POST.get('quota', '')
        price_raw = request.POST.get('price', '')
        error = validate_category_input(event_id, name, quota_raw, price_raw, events)
        if error:
            messages.error(request, error)
        else:
            event = get_object_or_404(events, pk=event_id)
            quota = int(quota_raw)
            total_quota = TicketCategory.objects.filter(event=event).exclude(pk=category.pk).aggregate(total=Sum('quota'))['total'] or 0
            if event.venue and total_quota + quota > event.venue.capacity:
                messages.error(request, 'Total kuota kategori tiket tidak boleh melebihi kapasitas venue.')
            else:
                category.event = event
                category.name = name
                category.quota = quota
                category.price = price_raw
                category.save()
                messages.success(request, 'Kategori tiket berhasil diperbarui.')
                return redirect('ticket_category_list')
    return render(request, 'tickets/category_form.html', {'events': events, 'category': category, 'action': 'update'})


@login_required
def ticket_category_delete_view(request, pk):
    if not can_manage_category(request.user):
        messages.error(request, 'Anda tidak memiliki izin untuk menghapus kategori tiket.')
        return redirect('ticket_category_list')
    category = get_object_or_404(category_scope(request.user), pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Kategori tiket berhasil dihapus.')
        return redirect('ticket_category_list')
    return render(request, 'tickets/category_confirm_delete.html', {'category': category})


def validate_category_input(event_id, name, quota_raw, price_raw, events):
    if not all([event_id, name, quota_raw, price_raw]):
        return 'Semua field wajib diisi.'
    if not events.filter(pk=event_id).exists():
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
