#!/usr/bin/env python
"""Comprehensive fix untuk semua incorrect column references"""
import os
import re

# Table-specific ID column mappings
REPLACEMENTS = {
    'accounts/views.py': [
        (r'WHERE\s+id\s*=', 'WHERE user_id ='),  # user_account.id -> user_account.user_id
    ],
    'orders/views.py': [
        (r'FROM\s+promotion\s+WHERE\s+id\s*=', 'FROM promotion WHERE promotion_id ='),
        (r'FROM\s+promotion\s+WHERE.*AND\s+id\s+!=', 'FROM promotion WHERE ... AND promotion_id !='),
        (r'FROM\s+ticket_category\s+ORDER\s+BY\s+id', 'FROM ticket_category ORDER BY category_id'),
        (r'FROM\s+ticket_category\s+WHERE\s+id\s*=', 'FROM ticket_category WHERE category_id ='),
        (r'FROM\s+"order"\s+WHERE\s+id\s*=', 'FROM "ORDER" WHERE order_id ='),  # Also fix table name
        (r'FROM\s+"ORDER"\s+WHERE\s+id\s*=', 'FROM "ORDER" WHERE order_id ='),
    ],
    'tickets/views.py': [
        (r'FROM\s+seat\s+WHERE\s+id\s+NOT\s+IN', 'FROM seat WHERE seat_id NOT IN'),
        (r'FROM\s+ticket_category\s+WHERE\s+id\s*=', 'FROM ticket_category WHERE category_id ='),
        (r'FROM\s+seat\s+WHERE\s+id\s*=', 'FROM seat WHERE seat_id ='),
        (r'WHERE\s+venue_id\s*=.*id\s+NOT\s+IN', 'WHERE venue_id = ... AND seat_id NOT IN'),
        (r'FROM\s+ticket\s+WHERE\s+id\s*=', 'FROM ticket WHERE ticket_id ='),
        (r'FROM\s+ticket_category\s+WHERE.*AND\s+id\s+!=', 'FROM ticket_category WHERE ... AND category_id !='),
        (r'FROM\s+ticket_category\s+WHERE\s+id\s*=', 'FROM ticket_category WHERE category_id ='),
    ],
    'seats/views.py': [
        (r'FROM\s+venue\s+WHERE\s+id\s*=', 'FROM venue WHERE venue_id ='),
        (r'FROM\s+seat\s+WHERE\s+id\s*=', 'FROM seat WHERE seat_id ='),
        (r'AND\s+id\s+!=', 'AND seat_id !='),
    ],
}

# Read each file and apply more targeted fixes
for filepath, rules in REPLACEMENTS.items():
    full_path = filepath
    if not os.path.exists(full_path):
        print(f"Skipping {filepath} - file not found")
        continue
    
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # For now, just print what needs to be fixed - manual approach
    print(f"\n=== {filepath} ===")
    for i, line in enumerate(content.split('\n'), 1):
        if 'WHERE' in line and ' id ' in line and 'SELECT' in content[max(0, content.find(line)-200):]:
            if 'id =' in line or 'id !=' in line or 'id NOT' in line or 'ORDER BY id' in line:
                print(f"  Line {i}: {line.strip()}")

print("\nDone! Manual replacements needed based on context above.")
