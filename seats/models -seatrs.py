import uuid
from django.db import models
from venues.models import Venue


class Seat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='seats')
    section = models.CharField(max_length=100)
    row = models.CharField(max_length=20)
    number = models.CharField(max_length=20)

    class Meta:
        unique_together = ('venue', 'section', 'row', 'number')
        ordering = ['venue__name', 'section', 'row', 'number']

    def label(self):
        return f'{self.section} - Baris {self.row}, No. {self.number}'

    def __str__(self):
        return f'{self.venue.name} - {self.label()}'
