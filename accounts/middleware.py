"""
Custom authentication middleware dengan 100% raw SQL (tanpa User model)
"""
from django.db import connection
from django.shortcuts import redirect
from functools import wraps
from accounts.backends import RawSQLBackend  # hapus AnonymousUser dari sini
from django.contrib.auth.models import AnonymousUser  # ← ambil dari Django


def get_user_from_session(request):
    """Load user dari session tanpa query User model - pure raw SQL"""
    SESSION_KEY = '_auth_user_id'
    
    # Cek apakah session ada
    if not hasattr(request, 'session') or not request.session:
        print(f"[DEBUG] Tidak ada session untuk request ke {request.path}")
        return AnonymousUser()  # Return anonymous user, bukan None
    
    # Ambil user_id dari session
    user_id = request.session.get(SESSION_KEY)
    print(f"[DEBUG] Session keys: {list(request.session.keys())}, user_id: {user_id}")
    
    if not user_id:
        print(f"[DEBUG] user_id tidak ada di session untuk request ke {request.path}")
        return AnonymousUser()  # Return anonymous user, bukan None
    
    # Gunakan custom RawSQLBackend untuk load user (tanpa django.contrib.auth)
    backend = RawSQLBackend()
    user = backend.get_user(user_id)
    
    print(f"[DEBUG] Loaded user dari backend: {user}")
    
    if user:
        # Tandai backend yang digunakan
        user.backend = 'accounts.backends.RawSQLBackend'
        return user
    
    # Jika user tidak ditemukan, return anonymous user
    print(f"[DEBUG] User tidak ditemukan untuk user_id {user_id}")
    return AnonymousUser()


def raw_sql_login_required(view_func):
    """
    Custom login_required decorator yang tidak bergantung pada Django auth.
    Gunakan ini untuk menggantikan @login_required dari django.contrib.auth.decorators
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = get_user_from_session(request)
        
        # Check apakah user authenticated (bukan anonymous)
        if not user.is_authenticated:
            # Redirect ke login jika belum authenticated
            return redirect('login')
        
        # Set request.user
        request.user = user
        
        # Call view function
        return view_func(request, *args, **kwargs)
    
    return wrapper


class RawSQLAuthenticationMiddleware:
    """
    Custom authentication middleware yang menggunakan raw SQL backend
    dan tidak query Django's User model sama sekali.
    
    Ganti 'django.contrib.auth.middleware.AuthenticationMiddleware' 
    dengan 'accounts.middleware.RawSQLAuthenticationMiddleware' di settings.py
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Load user dari session dengan custom logic (raw SQL only)
        # TIDAK PAKAI SimpleLazyObject agar template bisa evaluate dengan baik
        request.user = get_user_from_session(request)
        
        response = self.get_response(request)
        return response
