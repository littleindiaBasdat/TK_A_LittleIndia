import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tiktaktuk.settings')
django.setup()

from django.db import connection

# Check the order we just created
print("=== Latest order ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT o.order_id, o.order_date, o.payment_status, o.total_amount,
               c.full_name as customer_name,
               COUNT(t.ticket_id) as ticket_count,
               STRING_AGG(DISTINCT e.event_title, ', ') as events
        FROM "ORDER" o
        LEFT JOIN customer c ON o.customer_id = c.customer_id
        LEFT JOIN ticket t ON o.order_id = t.order_id
        LEFT JOIN ticket_category tc ON t.category_id = tc.category_id
        LEFT JOIN event e ON tc.event_id = e.event_id
        GROUP BY o.order_id, o.order_date, o.payment_status, o.total_amount, c.full_name
        ORDER BY o.order_date DESC
        LIMIT 1
    """)
    result = cursor.fetchone()
    if result:
        print(f"  order_id: {result[0]}")
        print(f"  order_date: {result[1]}")
        print(f"  payment_status: {result[2]}")
        print(f"  total_amount: {result[3]}")
        print(f"  customer_name: {result[4]}")
        print(f"  ticket_count: {result[5]}")
        print(f"  events: {result[6]}")
    else:
        print("  No orders found!")

# Count orders by status
print("\n=== Orders by status ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT payment_status, COUNT(*) as count
        FROM "ORDER"
        GROUP BY payment_status
    """)
    results = cursor.fetchall()
    for row in results:
        print(f"  {row[0]}: {row[1]}")

# Check order total and stats
print("\n=== Order statistics ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN payment_status = 'Lunas' THEN 1 ELSE 0 END) as paid_count,
            SUM(CASE WHEN payment_status = 'Pending' THEN 1 ELSE 0 END) as pending_count,
            COALESCE(SUM(CASE WHEN payment_status = 'Lunas' THEN total_amount ELSE 0 END), 0) as revenue
        FROM "ORDER"
    """)
    result = cursor.fetchone()
    print(f"  total_orders: {result[0]}")
    print(f"  paid_count: {result[1]}")
    print(f"  pending_count: {result[2]}")
    print(f"  revenue: {result[3]}")
