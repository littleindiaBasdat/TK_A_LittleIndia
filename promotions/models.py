import uuid
from django.db import models


class Promotion(models.Model):
    DISCOUNT_CHOICES = [
        ('percent', 'Persentase'),
        ('nominal', 'Nominal'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    promo_code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_CHOICES)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    usage_limit = models.PositiveIntegerField()
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['promo_code']

    def __str__(self):
        return self.promo_code
