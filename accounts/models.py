import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


class UserAccount(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('organizer', 'Organizer'),
        ('customer', 'Customer'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    phone = models.CharField(max_length=20, blank=True, null=True)
    full_name = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class OrganizerProfile(models.Model):
    user = models.OneToOneField(UserAccount, on_delete=models.CASCADE, related_name='organizer_profile')
    organizer_name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.organizer_name


class CustomerProfile(models.Model):
    user = models.OneToOneField(UserAccount, on_delete=models.CASCADE, related_name='customer_profile')

    def __str__(self):
        return f"Customer: {self.user.full_name}"
