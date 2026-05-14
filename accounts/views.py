from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import connection
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from accounts.middleware import raw_sql_login_required
import uuid

from django.contrib.sessions.backends.db import SessionStore


def create_session_raw_sql(request, user_id):
    session_key = str(uuid.uuid4()).replace('-', '')[:40]

    session_dict = {
        '_auth_user_id': str(user_id),
        '_auth_user_backend': 'accounts.backends.RawSQLBackend',
        '_auth_user_hash': '',
    }

    store = SessionStore()
    encoded_data = store.encode(session_dict)

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO django_session (session_key, session_data, expire_date)
               VALUES (%s, %s, %s)""",
            [session_key, encoded_data,
             timezone.now() + timezone.timedelta(days=7)]
        )

    return session_key


def get_user_role(user_id):
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


def _fmt_currency(amount):
    amount = float(amount)
    if amount >= 1_000_000:
        m = amount / 1_000_000
        return f"Rp {m:.1f}M" if m != int(m) else f"Rp {int(m)}M"
    elif amount >= 1_000:
        return f"Rp {amount/1_000:.0f}K"
    return f"Rp {int(amount):,}"


def _get_user_id(user):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM user_account WHERE username = %s",
            [user.username]
        )
        row = cursor.fetchone()
    return row[0] if row else user.id


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
    session_key = request.session.session_key if hasattr(request, 'session') else None
    if session_key:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM django_session WHERE session_key = %s",
                [session_key]
            )
    return redirect('login')


@raw_sql_login_required
def dashboard_view(request):
    user = request.user
    user_id = _get_user_id(user)
    user_role = get_user_role(user_id)
    context = {'user_role': user_role, 'username': user.username}

    with connection.cursor() as cursor:

        # ------------------------------------------------------------------ #
        # ADMIN
        # ------------------------------------------------------------------ #
        if user_role == 'admin':
            cursor.execute("SELECT COUNT(*) FROM user_account")
            total_users = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM event
                   WHERE DATE_TRUNC('month', event_datetime) = DATE_TRUNC('month', NOW())"""
            )
            total_events_month = cursor.fetchone()[0]

            cursor.execute('SELECT COALESCE(SUM(total_amount), 0) FROM "ORDER"')
            omzet = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM promotion
                   WHERE start_date <= CURRENT_DATE AND end_date >= CURRENT_DATE"""
            )
            active_promos = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM venue")
            total_venues = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM venue WHERE has_reserved_seating = TRUE")
            reserved_venues = cursor.fetchone()[0]

            cursor.execute("SELECT COALESCE(MAX(capacity), 0) FROM venue")
            max_capacity = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM promotion WHERE discount_type = 'PERCENTAGE'"
            )
            promo_percentage = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM promotion WHERE discount_type = 'NOMINAL'"
            )
            promo_nominal = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM order_promotion")
            total_promo_usage = cursor.fetchone()[0]

            context.update({
                'total_users': f"{total_users:,}",
                'total_events_month': f"{total_events_month:,}",
                'omzet': _fmt_currency(omzet),
                'active_promos': active_promos,
                'total_venues': total_venues,
                'reserved_venues': reserved_venues,
                'max_capacity': f"{max_capacity:,}",
                'promo_percentage': promo_percentage,
                'promo_nominal': promo_nominal,
                'total_promo_usage': total_promo_usage,
            })

        # ------------------------------------------------------------------ #
        # ORGANIZER
        # ------------------------------------------------------------------ #
        elif user_role == 'organizer':
            cursor.execute(
                "SELECT organizer_id, organizer_name FROM organizer WHERE user_id = %s",
                [user_id]
            )
            org_row = cursor.fetchone()
            if not org_row:
                messages.error(request, 'Data organizer tidak ditemukan.')
                return redirect('login')
            organizer_id, organizer_name = org_row

            cursor.execute(
                """SELECT COUNT(*) FROM event
                   WHERE organizer_id = %s AND event_datetime > NOW()""",
                [organizer_id]
            )
            active_events = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM ticket t
                   JOIN ticket_category tc ON t.category_id = tc.category_id
                   WHERE tc.event_id IN (SELECT event_id FROM event WHERE organizer_id = %s)""",
                [organizer_id]
            )
            tickets_sold = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COALESCE(SUM(o.total_amount), 0) FROM "ORDER" o
                   WHERE o.payment_status = 'Lunas' AND o.order_id IN (
                       SELECT DISTINCT t.order_id FROM ticket t
                       JOIN ticket_category tc ON t.category_id = tc.category_id
                       WHERE tc.event_id IN (SELECT event_id FROM event WHERE organizer_id = %s)
                   )""",
                [organizer_id]
            )
            revenue = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(DISTINCT venue_id) FROM event WHERE organizer_id = %s",
                [organizer_id]
            )
            venue_count = cursor.fetchone()[0]

            cursor.execute(
                """SELECT e.event_title, e.event_datetime, v.venue_name, v.city,
                          COALESCE(tc_total.total_quota, 0),
                          COALESCE(t_sold.sold, 0),
                          CASE WHEN e.event_datetime > NOW() THEN 'LIVE' ELSE 'ENDED' END
                   FROM event e
                   JOIN venue v ON e.venue_id = v.venue_id
                   LEFT JOIN (
                       SELECT event_id, SUM(quota) AS total_quota
                       FROM ticket_category GROUP BY event_id
                   ) tc_total ON e.event_id = tc_total.event_id
                   LEFT JOIN (
                       SELECT tc.event_id, COUNT(*) AS sold
                       FROM ticket t
                       JOIN ticket_category tc ON t.category_id = tc.category_id
                       GROUP BY tc.event_id
                   ) t_sold ON e.event_id = t_sold.event_id
                   WHERE e.organizer_id = %s
                   ORDER BY e.event_datetime DESC
                   LIMIT 5""",
                [organizer_id]
            )
            performa_events = []
            for row in cursor.fetchall():
                title, dt, venue_name, city, total_quota, sold, status = row
                pct = round(sold / total_quota * 100) if total_quota > 0 else 0
                performa_events.append({
                    'title': title,
                    'datetime': dt,
                    'venue_name': venue_name,
                    'city': city,
                    'pct': pct,
                    'status': status,
                })

            context.update({
                'organizer_name': organizer_name,
                'active_events': active_events,
                'tickets_sold': f"{tickets_sold:,}",
                'revenue': _fmt_currency(revenue),
                'venue_count': venue_count,
                'performa_events': performa_events,
            })

        # ------------------------------------------------------------------ #
        # CUSTOMER
        # ------------------------------------------------------------------ #
        else:
            cursor.execute(
                "SELECT customer_id, full_name FROM customer WHERE user_id = %s",
                [user_id]
            )
            cust_row = cursor.fetchone()
            if not cust_row:
                messages.error(request, 'Data customer tidak ditemukan.')
                return redirect('login')
            customer_id, customer_name = cust_row

            cursor.execute(
                """SELECT COUNT(*) FROM ticket t
                   JOIN "ORDER" o ON t.order_id = o.order_id
                   WHERE o.customer_id = %s AND o.payment_status = 'Lunas'""",
                [customer_id]
            )
            active_tickets = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(DISTINCT tc.event_id) FROM ticket t
                   JOIN ticket_category tc ON t.category_id = tc.category_id
                   JOIN "ORDER" o ON t.order_id = o.order_id
                   WHERE o.customer_id = %s""",
                [customer_id]
            )
            events_attended = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COUNT(*) FROM promotion
                   WHERE start_date <= CURRENT_DATE AND end_date >= CURRENT_DATE"""
            )
            active_promos = cursor.fetchone()[0]

            cursor.execute(
                """SELECT COALESCE(SUM(total_amount), 0) FROM "ORDER"
                   WHERE customer_id = %s AND payment_status = 'Lunas'""",
                [customer_id]
            )
            total_belanja = cursor.fetchone()[0]

            cursor.execute(
                """SELECT e.event_title, tc.category_name, e.event_datetime,
                          v.venue_name, v.city
                   FROM ticket t
                   JOIN ticket_category tc ON t.category_id = tc.category_id
                   JOIN event e ON tc.event_id = e.event_id
                   JOIN venue v ON e.venue_id = v.venue_id
                   JOIN "ORDER" o ON t.order_id = o.order_id
                   WHERE o.customer_id = %s AND e.event_datetime > NOW()
                   ORDER BY e.event_datetime
                   LIMIT 5""",
                [customer_id]
            )
            upcoming_tickets = []
            for row in cursor.fetchall():
                title, category, dt, venue_name, city = row
                upcoming_tickets.append({
                    'event_title': title,
                    'category_name': category,
                    'event_datetime': dt,
                    'venue_name': venue_name,
                    'city': city,
                })

            cursor.execute(
                """SELECT COUNT(DISTINCT e.event_id)
                   FROM ticket t
                   JOIN ticket_category tc ON t.category_id = tc.category_id
                   JOIN event e ON tc.event_id = e.event_id
                   JOIN "ORDER" o ON t.order_id = o.order_id
                   WHERE o.customer_id = %s AND e.event_datetime > NOW()""",
                [customer_id]
            )
            upcoming_count = cursor.fetchone()[0]

            context.update({
                'customer_name': customer_name,
                'upcoming_count': upcoming_count,
                'active_tickets': active_tickets,
                'events_attended': events_attended,
                'active_promos': active_promos,
                'total_belanja': _fmt_currency(total_belanja),
                'upcoming_tickets': upcoming_tickets,
            })

    return render(request, 'accounts/dashboard.html', context)


@raw_sql_login_required
def profile_edit_view(request):
    user = request.user
    user_id = _get_user_id(user)
    user_role = get_user_role(user_id)

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')

        # ---- Update profile info ----------------------------------------- #
        if form_type == 'profile':
            with connection.cursor() as cursor:
                if user_role == 'customer':
                    full_name = request.POST.get('full_name', '').strip()
                    phone = request.POST.get('phone', '').strip()
                    if not full_name:
                        messages.error(request, 'Nama lengkap wajib diisi.')
                    else:
                        cursor.execute(
                            "UPDATE customer SET full_name = %s, phone_number = %s WHERE user_id = %s",
                            [full_name, phone, user_id]
                        )
                        messages.success(request, 'Profil berhasil diperbarui.')
                elif user_role == 'organizer':
                    organizer_name = request.POST.get('organizer_name', '').strip()
                    contact_email = request.POST.get('contact_email', '').strip()
                    if not organizer_name:
                        messages.error(request, 'Nama organizer wajib diisi.')
                    else:
                        cursor.execute(
                            "UPDATE organizer SET organizer_name = %s, contact_email = %s WHERE user_id = %s",
                            [organizer_name, contact_email, user_id]
                        )
                        messages.success(request, 'Profil berhasil diperbarui.')

        # ---- Update password --------------------------------------------- #
        elif form_type == 'password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT password FROM user_account WHERE user_id = %s",
                    [user_id]
                )
                row = cursor.fetchone()

            if not row:
                messages.error(request, 'User tidak ditemukan.')
            elif not check_password(old_password, row[0]):
                messages.error(request, 'Password lama salah.')
            elif new_password != confirm_password:
                messages.error(request, 'Password baru tidak cocok.')
            elif len(new_password) < 8:
                messages.error(request, 'Password minimal 8 karakter.')
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE user_account SET password = %s WHERE user_id = %s",
                        [make_password(new_password), user_id]
                    )
                messages.success(request, 'Password berhasil diperbarui.')

        return redirect('profile_edit')

    # GET — load current profile data
    profile = {}
    with connection.cursor() as cursor:
        if user_role == 'customer':
            cursor.execute(
                "SELECT full_name, phone_number FROM customer WHERE user_id = %s",
                [user_id]
            )
            row = cursor.fetchone()
            if row:
                profile = {'full_name': row[0] or '', 'phone': row[1] or ''}
        elif user_role == 'organizer':
            cursor.execute(
                "SELECT organizer_name, contact_email FROM organizer WHERE user_id = %s",
                [user_id]
            )
            row = cursor.fetchone()
            if row:
                profile = {'organizer_name': row[0] or '', 'contact_email': row[1] or ''}

    return render(request, 'accounts/profile_edit.html', {
        'profile': profile,
        'user_role': user_role,
        'username': user.username,
    })


# Kept for backward-compat (URL still registered), redirects to profile_edit
@raw_sql_login_required
def password_update_view(request):
    return redirect('profile_edit')
