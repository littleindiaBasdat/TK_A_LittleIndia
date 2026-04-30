import uuid
from django.db import models
from events.models import Event
from orders.models import Order
from seats.models import Seat


class TicketCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticket_categories')
    name = models.CharField(max_length=100)
    quota = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['event__title', 'name']

    def __str__(self):
        return f'{self.event.title} - {self.name}'


class Ticket(models.Model):
    STATUS_CHOICES = [
        ('active', 'Aktif'),
        ('used', 'Digunakan'),
        ('cancelled', 'Dibatalkan'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tickets')
    category = models.ForeignKey(TicketCategory, on_delete=models.CASCADE, related_name='tickets')
    seat = models.OneToOneField(Seat, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code
