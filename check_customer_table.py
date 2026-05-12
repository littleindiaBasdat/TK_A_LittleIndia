import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tiktaktuk.settings')
django.setup()

from django.db import connection

print("=== Customer table structure ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'customer'
        ORDER BY ordinal_position
    """)
    results = cursor.fetchall()
    for row in results:
        print(f"  {row[0]}: {row[1]} (nullable: {row[2]})")

print("\n=== Primary key for customer table ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name = 'customer' AND constraint_type = 'PRIMARY KEY'
    """)
    result = cursor.fetchone()
    print(f"  {result[0] if result else 'NONE'}")

print("\n=== Checking johndoe2 user record ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT user_id, username
        FROM user_account
        WHERE username = 'johndoe2'
    """)
    user_result = cursor.fetchone()
    if user_result:
        user_id, username = user_result
        print(f"  Found: user_id={user_id}, username={username}")
        
        # Check customer record
        cursor.execute("""
            SELECT * FROM customer WHERE user_id = %s
        """, [user_id])
        cust_result = cursor.fetchone()
        if cust_result:
            print(f"  Customer record EXISTS: {cust_result}")
        else:
            print(f"  Customer record MISSING for user_id={user_id}")
    else:
        print("  johndoe2 user account not found!")

print("\n=== All customer records ===")
with connection.cursor() as cursor:
    cursor.execute("SELECT * FROM customer LIMIT 5")
    results = cursor.fetchall()
    for row in results:
        print(f"  {row}")
