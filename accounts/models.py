import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserAccount(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('organizer', 'Organizer'),
        ('customer', 'Customer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    organizer_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)

    def display_name(self):
        if self.role == 'organizer' and self.organizer_name:
            return self.organizer_name
        return self.full_name or self.username

    def __str__(self):
        return f'{self.username} ({self.role})'
