import uuid
from django.conf import settings
from django.db import models
from venues.models import Venue


class Artist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    genre = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    date = models.DateField()
    time = models.TimeField()
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, related_name='events')
    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='organized_events')
    artists = models.ManyToManyField(Artist, blank=True, related_name='events')
    description = models.TextField(blank=True)

    def __str__(self):
        return self.title
