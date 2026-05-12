#!/usr/bin/env python
"""Fix all remaining column name mismatches"""
import os

# Define column name mappings
FIXES = {
    'tickets/views.py': [
        ('e.title', 'e.event_title'),
        ('v.name', 'v.venue_name'),
        ('tc.name', 'tc.category_name'),
        ('LOWER(t.code)', 'LOWER(t.ticket_code)'),  # ticket table uses ticket_code not code
    ],
    'orders/views.py': [
        # Nothing else needed - already checked
    ],
    'seats/views.py': [
        ('s.section, s.row, s.number', 's.section, s.row_number, s.seat_number'),
    ],
}

for filepath, replacements in FIXES.items():
    if not os.path.exists(filepath):
        continue
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    for old, new in replacements:
        content = content.replace(old, new)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Fixed {filepath}")
    else:
        print(f"  No changes in {filepath}")

print("Done!")
