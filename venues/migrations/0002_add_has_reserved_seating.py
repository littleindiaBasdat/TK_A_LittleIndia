from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('venues', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE venue ADD COLUMN IF NOT EXISTS has_reserved_seating BOOLEAN NOT NULL DEFAULT FALSE;",
            reverse_sql="ALTER TABLE venue DROP COLUMN IF EXISTS has_reserved_seating;",
        ),
    ]
