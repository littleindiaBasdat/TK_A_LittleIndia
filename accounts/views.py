from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from tickets.models import Ticket
from orders.models import Order
from seats.models import Seat
from events.models import Event
from .models import UserAccount


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        try:
            user_obj = UserAccount.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)
        except UserAccount.DoesNotExist:
            user = None
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Email atau password salah.')
    return render(request, 'accounts/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        role = request.POST.get('role', 'customer')
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        if role not in ['admin', 'organizer', 'customer']:
            messages.error(request, 'Role tidak valid.')
        elif not all([username, email, password, password2]):
            messages.error(request, 'Semua field akun wajib diisi.')
        elif password != password2:
            messages.error(request, 'Password tidak cocok.')
        elif UserAccount.objects.filter(username=username).exists():
            messages.error(request, 'Username sudah digunakan.')
        elif UserAccount.objects.filter(email=email).exists():
            messages.error(request, 'Email sudah terdaftar.')
        else:
            user = UserAccount(username=username, email=email, role=role)
            user.full_name = request.POST.get('full_name', '').strip()
            user.phone = request.POST.get('phone', '').strip()
            user.organizer_name = request.POST.get('organizer_name', '').strip()
            user.contact_email = request.POST.get('contact_email', '').strip()
            user.is_staff = role == 'admin'
            user.set_password(password)
            user.save()
            messages.success(request, 'Akun berhasil dibuat. Silakan login.')
            return redirect('login')
    return render(request, 'accounts/register.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    user = request.user
    if user.role == 'customer':
        tickets_count = Ticket.objects.filter(order__customer=user).count()
        orders_count = Order.objects.filter(customer=user).count()
        events_count = Event.objects.count()
    elif user.role == 'organizer':
        tickets_count = Ticket.objects.filter(order__event__organizer=user).count()
        orders_count = Order.objects.filter(event__organizer=user).count()
        events_count = Event.objects.filter(organizer=user).count()
    else:
        tickets_count = Ticket.objects.count()
        orders_count = Order.objects.count()
        events_count = Event.objects.count()
    return render(request, 'accounts/dashboard.html', {
        'tickets_count': tickets_count,
        'orders_count': orders_count,
        'events_count': events_count,
        'seats_count': Seat.objects.count(),
    })


@login_required
def profile_edit_view(request):
    if request.method == 'POST':
        user = request.user
        if user.role == 'organizer':
            user.organizer_name = request.POST.get('organizer_name', user.organizer_name).strip()
            user.contact_email = request.POST.get('contact_email', user.contact_email).strip()
        elif user.role == 'customer':
            user.full_name = request.POST.get('full_name', user.full_name).strip()
            user.phone = request.POST.get('phone', user.phone).strip()
        else:
            user.full_name = request.POST.get('full_name', user.full_name).strip()
            user.email = request.POST.get('email', user.email).strip()
        user.save()
        messages.success(request, 'Profil berhasil diperbarui.')
        return redirect('dashboard')
    return render(request, 'accounts/profile_edit.html')


@login_required
def password_update_view(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        user = request.user
        if not user.check_password(old_password):
            messages.error(request, 'Password lama salah.')
        elif new_password != confirm_password:
            messages.error(request, 'Password baru tidak cocok.')
        elif len(new_password) < 8:
            messages.error(request, 'Password minimal 8 karakter.')
        else:
            user.set_password(new_password)
            user.save()
            login(request, user)
            messages.success(request, 'Password berhasil diperbarui.')
            return redirect('dashboard')
    return render(request, 'accounts/password_update.html')
