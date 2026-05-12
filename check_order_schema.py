#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tiktaktuk.settings')
import django
django.setup()
from django.db import connection

with connection.cursor() as cursor:
    # Check ORDER table columns
    cursor.execute("""SELECT column_name, data_type FROM information_schema.columns 
                      WHERE table_name='ORDER' ORDER BY ordinal_position""")
    cols = cursor.fetchall()
    print('ORDER table columns:')
    for col in cols:
        print(f'  - {col[0]} ({col[1]})')
    print()
    
    # Check order_promotion table
    cursor.execute("""SELECT column_name, data_type FROM information_schema.columns 
                      WHERE table_name='order_promotion' ORDER BY ordinal_position""")
    cols = cursor.fetchall()
    print('order_promotion table columns:')
    for col in cols:
        print(f'  - {col[0]} ({col[1]})')
    print()
    
    # Check first few records in order_promotion
    cursor.execute("SELECT * FROM order_promotion LIMIT 3")
    rows = cursor.fetchall()
    print('First 3 rows in order_promotion:')
    for row in rows:
        print(f'  {row}')
