import uuid
from django.db import models


class Venue(models.Model):
    SEATING_CHOICES = [
        ('reserved', 'Reserved Seating'),
        ('free', 'Free Seating'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    address = models.TextField()
    city = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField()
    seating_type = models.CharField(max_length=20, choices=SEATING_CHOICES, default='free')

    def __str__(self):
        return f"{self.name} - {self.city}"
