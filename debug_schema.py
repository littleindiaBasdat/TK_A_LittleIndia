#!/usr/bin/env python
"""Debug script untuk check schema dari order dan related tables"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tiktaktuk.settings')
django.setup()

from django.db import connection

tables_to_check = ['ORDER', 'ticket', 'order_promotion', 'event', 'venue', 'customer', 'organizer', 'artist', 'promotion', 'seat']

for table_name in tables_to_check:
    print(f"\n{'='*60}")
    print(f"Table: {table_name}")
    print('='*60)
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name=%s
                ORDER BY ordinal_position
            """, [table_name])
            columns = cursor.fetchall()
            
            if columns:
                for col_name, data_type in columns:
                    print(f"  {col_name:<30} {data_type}")
            else:
                print(f"  Table '{table_name}' not found!")
    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "="*60)
