from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE event ADD COLUMN IF NOT EXISTS description TEXT;",
            reverse_sql="ALTER TABLE event DROP COLUMN IF EXISTS description;",
        ),
    ]
