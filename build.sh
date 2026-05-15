#!/usr/bin/env bash
# Script yang dijalankan Render saat deploy
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Kumpulkan static files (CSS, JS) ke STATIC_ROOT supaya WhiteNoise bisa serve
python manage.py collectstatic --no-input

# Jika kamu pakai Django migrations untuk admin/auth/sessions (yang 22 unapplied tadi),
# uncomment baris di bawah:
# python manage.py migrate --no-input