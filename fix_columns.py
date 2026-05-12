#!/usr/bin/env python
"""Auto-fix script untuk replace incorrect column references dengan yang benar"""
import os
import re

# Schema map: old_column_name -> correct_column_name berdasarkan real database
COLUMN_FIXES = {
    r'e\.id': 'e.event_id',  # event.id -> event.event_id
    r'v\.id': 'v.venue_id',  # venue.id -> venue.venue_id
    r'p\.id': 'p.promotion_id',  # promotion.id -> promotion.promotion_id
    r's\.id': 's.seat_id',  # seat.id -> seat.seat_id
    r'c\.id': 'c.customer_id',  # customer.id -> customer.customer_id
    r'o\.id': 'o.order_id',  # order.id -> order.order_id (already done)
    r't\.id': 't.ticket_id',  # ticket.id -> ticket.ticket_id
    r'tc\.id': 'tc.category_id',  # ticket_category.id -> ticket_category.category_id
    r'a\.id': 'a.artist_id',  # artist.id -> artist.artist_id
}

# Files to fix
files_to_fix = [
    'accounts/views.py',
    'orders/views.py',
    'seats/views.py',
    'tickets/views.py',
]

for filepath in files_to_fix:
    if not os.path.exists(filepath):
        print(f"Skipping {filepath} - file not found")
        continue
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Apply all fixes
    for old_pattern, new_column in COLUMN_FIXES.items():
        content = re.sub(old_pattern, new_column, content)
    
    # Only write if changed
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Fixed {filepath}")
    else:
        print(f"  No changes needed in {filepath}")

print("\nColumn references fixed!")
