from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import UserAccount, OrganizerProfile, CustomerProfile


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
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Email atau password salah.')
    return render(request, 'accounts/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        role = request.POST.get('role')
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if role not in ['admin', 'organizer', 'customer']:
            messages.error(request, 'Role tidak valid.')
            return render(request, 'accounts/register.html')

        if not all([username, email, password, password2]):
            messages.error(request, 'Username, email, dan password wajib diisi.')
            return render(request, 'accounts/register.html', {'role': role})

        if password != password2:
            messages.error(request, 'Password tidak cocok.')
            return render(request, 'accounts/register.html', {'role': role})

        if UserAccount.objects.filter(username=username).exists():
            messages.error(request, 'Username sudah digunakan.')
            return render(request, 'accounts/register.html', {'role': role})

        if UserAccount.objects.filter(email=email).exists():
            messages.error(request, 'Email sudah terdaftar.')
            return render(request, 'accounts/register.html', {'role': role})

        user = UserAccount(username=username, email=email, role=role)
        user.set_password(password)

        if role == 'customer':
            full_name = request.POST.get('full_name', '').strip()
            phone = request.POST.get('phone', '').strip()
            user.full_name = full_name
            user.phone = phone
            user.save()
            CustomerProfile.objects.create(user=user)

        elif role == 'organizer':
            organizer_name = request.POST.get('organizer_name', '').strip()
            contact_email = request.POST.get('contact_email', '').strip()
            description = request.POST.get('description', '').strip()
            user.full_name = organizer_name
            user.save()
            OrganizerProfile.objects.create(user=user, organizer_name=organizer_name, contact_email=contact_email, description=description)

        elif role == 'admin':
            full_name = request.POST.get('full_name', '').strip()
            user.full_name = full_name
            user.is_staff = True
            user.save()

        messages.success(request, 'Akun berhasil dibuat! Silakan login.')
        return redirect('login')

    return render(request, 'accounts/register.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    user = request.user
    organizer_profile = None
    customer_profile = None
    if user.role == 'organizer':
        try:
            organizer_profile = user.organizer_profile
        except OrganizerProfile.DoesNotExist:
            pass
    elif user.role == 'customer':
        try:
            customer_profile = user.customer_profile
        except CustomerProfile.DoesNotExist:
            pass
    return render(request, 'accounts/dashboard.html', {
        'organizer_profile': organizer_profile,
        'customer_profile': customer_profile,
    })


@login_required
def profile_edit_view(request):
    user = request.user
    if request.method == 'POST':
        if user.role == 'customer':
            user.full_name = request.POST.get('full_name', user.full_name)
            user.phone = request.POST.get('phone', user.phone)
            user.save()
        elif user.role == 'organizer':
            try:
                profile = user.organizer_profile
                profile.organizer_name = request.POST.get('organizer_name', profile.organizer_name)
                profile.contact_email = request.POST.get('contact_email', profile.contact_email)
                profile.save()
            except OrganizerProfile.DoesNotExist:
                pass
        elif user.role == 'admin':
            user.full_name = request.POST.get('full_name', user.full_name)
            user.email = request.POST.get('email', user.email)
            user.save()
        messages.success(request, 'Profil berhasil diperbarui.')
        return redirect('dashboard')
    organizer_profile = None
    if user.role == 'organizer':
        try:
            organizer_profile = user.organizer_profile
        except OrganizerProfile.DoesNotExist:
            pass
    return render(request, 'accounts/profile_edit.html', {'organizer_profile': organizer_profile})


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
