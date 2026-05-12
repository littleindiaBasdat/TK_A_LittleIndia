import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tiktaktuk.settings')
django.setup()

from django.db import connection

# Check existing payment_status values
print("=== Existing payment_status values in ORDER table ===")
with connection.cursor() as cursor:
    cursor.execute('SELECT DISTINCT payment_status FROM "ORDER"')
    results = cursor.fetchall()
    if results:
        for row in results:
            print(f'  {repr(row[0])}')
    else:
        print("  (no records yet)")

# Check table constraints
print("\n=== Checking for CHECK constraints ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT constraint_name, constraint_type 
        FROM information_schema.table_constraints 
        WHERE table_name = 'ORDER'
    """)
    constraints = cursor.fetchall()
    if constraints:
        for name, ctype in constraints:
            print(f"  {name}: {ctype}")
    else:
        print("  (no constraints found)")

# Try inserting with different values to see what error we get
print("\n=== Testing INSERT with different payment_status values ===")
import uuid
from django.utils import timezone

test_values = ['PENDING', 'pending', 'PAID', 'paid', 'UNPAID', 'unpaid', 'CANCELLED', 'cancelled']

for status in test_values:
    try:
        test_id = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO "ORDER" (order_id, customer_id, total_amount, payment_status, order_date) VALUES (%s, %s, %s, %s, %s)',
                [test_id, '866d2cf4-d0b3-40de-ba05-10c6fdde64b6', 100, status, timezone.now()]
            )
        print(f"  ✓ {repr(status)} - SUCCESS (rolled back)")
        # Rollback to not pollute data
        connection.rollback()
    except Exception as e:
        error_msg = str(e)
        if 'check constraint' in error_msg.lower():
            print(f"  ✗ {repr(status)} - CHECK CONSTRAINT VIOLATION")
        else:
            print(f"  ✗ {repr(status)} - ERROR: {error_msg[:60]}")
