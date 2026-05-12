from django.db import connection


class RawUser:
    """
    Minimal user object kompatibel dengan Django auth middleware + template.
    Bukan Django Model — murni plain class, tanpa ORM sama sekali.
    Semua atribut yang dipakai navbar & dashboard sudah tersedia di sini.
    """
    is_active = True
    is_anonymous = False

    def __init__(self, user_id, username, role='customer',
                 display_name='', email='', phone='', contact_email=''):
        self.id = user_id
        self.pk = user_id
        self.username = username
        self.role = role           # 'admin' | 'organizer' | 'customer'
        self.display_name = display_name
        self.email = email
        self.phone = phone
        self.contact_email = contact_email

    @property
    def is_authenticated(self):
        return True

    def get_role_display(self):
        label = {'admin': 'Admin', 'organizer': 'Organizer', 'customer': 'Customer'}
        return label.get(self.role, self.role.title())

    def get_session_auth_hash(self):
        return ''

    def __str__(self):
        return self.username


class RawSQLBackend:
    """
    Custom authentication backend yang membaca dari tabel user_account
    menggunakan raw SQL — tanpa ORM sama sekali.
    Dipasang di settings.py:
        AUTHENTICATION_BACKENDS = ['accounts.backends.RawSQLBackend']
    """

    def authenticate(self, request, **kwargs):
        return None  # autentikasi ditangani manual di login_view

    def get_user(self, user_id):
        """
        Dipanggil AuthenticationMiddleware setiap request untuk restore
        user dari session. Load sekaligus role + data profil supaya
        template bisa pakai user.role, user.display_name, dll.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ua.user_id, ua.username, r.role_name
                FROM user_account ua
                LEFT JOIN account_role ar ON ar.user_id = ua.user_id
                LEFT JOIN role r ON r.role_id = ar.role_id
                WHERE ua.user_id = %s
                """,
                [user_id]
            )
            row = cursor.fetchone()

        if not row:
            return None

        uid, username, role = row[0], row[1], (row[2] or 'customer').lower()

        display_name = ''
        email = ''
        phone = ''
        contact_email = ''

        with connection.cursor() as cursor:
            if role == 'customer':
                cursor.execute(
                    "SELECT full_name, phone_number FROM customer WHERE user_id = %s",
                    [uid]
                )
                profile = cursor.fetchone()
                if profile:
                    display_name = profile[0] or ''
                    phone = profile[1] or ''

            elif role == 'organizer':
                cursor.execute(
                    "SELECT organizer_name, contact_email FROM organizer WHERE user_id = %s",
                    [uid]
                )
                profile = cursor.fetchone()
                if profile:
                    display_name = profile[0] or ''
                    contact_email = profile[1] or ''
                    email = contact_email

            elif role == 'admin':
                cursor.execute(
                    "SELECT full_name FROM customer WHERE user_id = %s",
                    [uid]
                )
                profile = cursor.fetchone()
                if profile:
                    display_name = profile[0] or ''

        return RawUser(
            user_id=uid,
            username=username,
            role=role,
            display_name=display_name,
            email=email,
            phone=phone,
            contact_email=contact_email,
        )