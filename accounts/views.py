from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import connection
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from accounts.middleware import raw_sql_login_required
import uuid


# ---------------------------------------------------------------------------
# Helper: buat Django session via raw SQL
# ---------------------------------------------------------------------------

# views.py

from django.contrib.sessions.backends.db import SessionStore  # tambah import ini

def create_session_raw_sql(request, user_id):
    session_key = str(uuid.uuid4()).replace('-', '')[:40]

    session_dict = {
        '_auth_user_id': str(user_id),
        '_auth_user_backend': 'accounts.backends.RawSQLBackend',
        '_auth_user_hash': '',
    }

    # GANTI INI — pakai encode() Django bukan JSONSerializer langsung
    # karena Django butuh signed data, bukan raw JSON
    store = SessionStore()
    encoded_data = store.encode(session_dict)  # ← ini yang benar

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO django_session (session_key, session_data, expire_date)
               VALUES (%s, %s, %s)""",
            [session_key, encoded_data,
             timezone.now() + timezone.timedelta(days=7)]
        )

    return session_key


# ---------------------------------------------------------------------------
# Helper: ambil role user
# ---------------------------------------------------------------------------

def get_user_role(user_id):
    """Ambil role dari tabel account_role via raw SQL."""
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT r.role_name
               FROM account_role ar
               JOIN role r ON ar.role_id = r.role_id
               WHERE ar.user_id = %s""",
            [user_id]
        )
        result = cursor.fetchone()
    return result[0] if result else 'customer'


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, password FROM user_account WHERE username = %s",
                [username]
            )
            user_row = cursor.fetchone()

        if user_row and check_password(password, user_row[1]):
            user_id = user_row[0]
            session_key = create_session_raw_sql(request, user_id)

            response = redirect('dashboard')

            from django.conf import settings
            response.set_cookie(
                settings.SESSION_COOKIE_NAME,
                session_key,
                max_age=settings.SESSION_COOKIE_AGE,
                expires=None,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                secure=settings.SESSION_COOKIE_SECURE,
                httponly=settings.SESSION_COOKIE_HTTPONLY,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            return response

        messages.error(request, 'Username atau password salah.')

    return render(request, 'accounts/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        role_name = request.POST.get('role', 'customer')
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if role_name not in ['admin', 'organizer', 'customer']:
            messages.error(request, 'Role tidak valid.')
        elif not all([username, password, password2]):
            messages.error(request, 'Username dan password wajib diisi.')
        elif password != password2:
            messages.error(request, 'Password tidak cocok.')
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM user_account WHERE username = %s",
                    [username]
                )
                if cursor.fetchone():
                    messages.error(request, 'Username sudah digunakan.')
                    return render(request, 'accounts/register.html')

            full_name = request.POST.get('full_name', '').strip()
            phone = request.POST.get('phone', '').strip()
            organizer_name = request.POST.get('organizer_name', '').strip()
            contact_email = request.POST.get('contact_email', '').strip()

            if role_name == 'customer' and not all([full_name, phone]):
                messages.error(request, 'Nama lengkap dan nomor telepon wajib diisi untuk customer.')
                return render(request, 'accounts/register.html')
            if role_name == 'organizer' and not all([organizer_name, contact_email]):
                messages.error(request, 'Nama organizer dan email kontak wajib diisi.')
                return render(request, 'accounts/register.html')
            if role_name == 'admin' and not full_name:
                messages.error(request, 'Nama admin wajib diisi.')
                return render(request, 'accounts/register.html')

            hashed_password = make_password(password)

            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO user_account (username, password) VALUES (%s, %s) RETURNING user_id",
                        [username, hashed_password]
                    )
                    user_id = cursor.fetchone()[0]

                    cursor.execute(
                        "SELECT role_id FROM role WHERE LOWER(role_name) = LOWER(%s)",
                        [role_name]
                    )
                    role_row = cursor.fetchone()
                    role_id = role_row[0] if role_row else 1

                    cursor.execute(
                        "INSERT INTO account_role (role_id, user_id) VALUES (%s, %s)",
                        [role_id, user_id]
                    )

                    if role_name == 'customer':
                        cursor.execute(
                            "INSERT INTO customer (user_id, full_name, phone_number) VALUES (%s, %s, %s)",
                            [user_id, full_name, phone]
                        )
                    elif role_name == 'organizer':
                        cursor.execute(
                            "INSERT INTO organizer (user_id, organizer_name, contact_email) VALUES (%s, %s, %s)",
                            [user_id, organizer_name, contact_email]
                        )

                messages.success(request, 'Akun berhasil dibuat. Silakan login.')
                return redirect('login')
            except Exception as e:
                messages.error(request, f'Terjadi kesalahan: {str(e)}')
                return render(request, 'accounts/register.html')

    return render(request, 'accounts/register.html')


@raw_sql_login_required
def logout_view(request):
    # Hapus session dari django_session via raw SQL
    session_key = request.session.session_key if hasattr(request, 'session') else None
    if session_key:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM django_session WHERE session_key = %s",
                [session_key]
            )
    
    # Redirect ke login (session sudah terhapus)
    return redirect('login')


@raw_sql_login_required
def dashboard_view(request):
    user = request.user

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM user_account WHERE username = %s",
            [user.username]
        )
        user_data = cursor.fetchone()
        user_id = user_data[0] if user_data else user.id

    user_role = get_user_role(user_id)

    with connection.cursor() as cursor:
        if user_role == 'customer':
            cursor.execute(
                """SELECT COUNT(*) FROM ticket WHERE order_id IN 
                   (SELECT o.order_id FROM \"ORDER\" o
                    JOIN customer c ON o.customer_id = c.customer_id
                    WHERE c.user_id = %s)""",
                [user_id]
            )
            tickets_count = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM "ORDER"
                   WHERE customer_id IN (SELECT customer_id FROM customer WHERE user_id = %s)""",
                [user_id]
            )
            orders_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM event")
            events_count = cursor.fetchone()[0]

        elif user_role == 'organizer':
            cursor.execute(
                """SELECT COUNT(*) FROM ticket WHERE order_id IN
                   (SELECT DISTINCT t.order_id FROM ticket t 
                    JOIN ticket_category tc ON t.category_id = tc.category_id
                    WHERE tc.event_id IN
                     (SELECT e.event_id FROM event e WHERE e.organizer_id IN
                      (SELECT organizer_id FROM organizer WHERE user_id = %s)))""",
                [user_id]
            )
            tickets_count = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM "ORDER" WHERE order_id IN
                   (SELECT DISTINCT t.order_id FROM ticket t
                    JOIN ticket_category tc ON t.category_id = tc.category_id
                    WHERE tc.event_id IN
                     (SELECT e.event_id FROM event e WHERE e.organizer_id IN
                      (SELECT organizer_id FROM organizer WHERE user_id = %s)))""",
                [user_id]
            )
            orders_count = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM event
                   WHERE organizer_id IN (SELECT organizer_id FROM organizer WHERE user_id = %s)""",
                [user_id]
            )
            events_count = cursor.fetchone()[0]

        else:  # admin
            cursor.execute("SELECT COUNT(*) FROM ticket")
            tickets_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM "ORDER"')
            orders_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM event")
            events_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM seat")
        seats_count = cursor.fetchone()[0]

    return render(request, 'accounts/dashboard.html', {
        'tickets_count': tickets_count,
        'orders_count': orders_count,
        'events_count': events_count,
        'seats_count': seats_count,
    })


@raw_sql_login_required
def profile_edit_view(request):
    user = request.user

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM user_account WHERE username = %s",
            [user.username]
        )
        user_data = cursor.fetchone()
        user_id = user_data[0] if user_data else user.id

    user_role = get_user_role(user_id)

    if request.method == 'POST':
        with connection.cursor() as cursor:
            if user_role == 'customer':
                full_name = request.POST.get('full_name', '').strip()
                phone = request.POST.get('phone', '').strip()
                cursor.execute(
                    "UPDATE customer SET full_name = %s, phone_number = %s WHERE user_id = %s",
                    [full_name, phone, user_id]
                )
            elif user_role == 'organizer':
                organizer_name = request.POST.get('organizer_name', '').strip()
                contact_email = request.POST.get('contact_email', '').strip()
                cursor.execute(
                    "UPDATE organizer SET organizer_name = %s, contact_email = %s WHERE user_id = %s",
                    [organizer_name, contact_email, user_id]
                )

        messages.success(request, 'Profil berhasil diperbarui.')
        return redirect('dashboard')

    # GET: siapkan data profil untuk ditampilkan di form
    profile = {}
    with connection.cursor() as cursor:
        if user_role == 'customer':
            cursor.execute(
                "SELECT full_name, phone_number FROM customer WHERE user_id = %s",
                [user_id]
            )
            row = cursor.fetchone()
            if row:
                profile = {'full_name': row[0], 'phone': row[1]}
        elif user_role == 'organizer':
            cursor.execute(
                "SELECT organizer_name, contact_email FROM organizer WHERE user_id = %s",
                [user_id]
            )
            row = cursor.fetchone()
            if row:
                profile = {'organizer_name': row[0], 'contact_email': row[1]}

    return render(request, 'accounts/profile_edit.html', {
        'profile': profile,
        'user_role': user_role,
    })


@raw_sql_login_required
def password_update_view(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        user = request.user

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, password FROM user_account WHERE username = %s",
                [user.username]
            )
            user_data = cursor.fetchone()
            if not user_data:
                messages.error(request, 'User tidak ditemukan.')
                return redirect('dashboard')
            user_id, stored_password = user_data

        if not check_password(old_password, stored_password):
            messages.error(request, 'Password lama salah.')
        elif new_password != confirm_password:
            messages.error(request, 'Password baru tidak cocok.')
        elif len(new_password) < 8:
            messages.error(request, 'Password minimal 8 karakter.')
        else:
            hashed_password = make_password(new_password)
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_account SET password = %s WHERE user_id = %s",
                    [hashed_password, user_id]
                )
            # Tidak perlu login() karena _auth_user_hash kita selalu ''
            # sehingga session tetap valid setelah ganti password
            messages.success(request, 'Password berhasil diperbarui.')
            return redirect('dashboard')

    return render(request, 'accounts/password_update.html')