import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tiktaktuk.settings')
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    # Check all public tables
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    print('Semua table:')
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        print(f'  - {table}')
    
    # Check kolom untuk setiap table penting
    for table_name in ['user_account', 'role', 'account_role', 'customer', 'organizer']:
        try:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position",
                [table_name]
            )
            cols = cursor.fetchall()
            if cols:
                print(f'\nKolom di {table_name}:')
                for row in cols:
                    print(f'  - {row[0]}')
        except Exception as e:
            pass
