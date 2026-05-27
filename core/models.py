from django.db import models
from django.contrib.auth.models import AbstractUser
import hashlib
from django.utils import timezone

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('supplier', 'Supplier'),
        ('manufacturer', 'Manufacturer'),
        ('wholesaler', 'Wholesaler'),
        ('distributor', 'Distributor'),
        ('customer', 'Customer'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_approved = models.BooleanField(default=False)  # Admin approves customers/stakeholders

    def __str__(self):
        return self.username

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class RawMaterial(models.Model):
    name = models.CharField(max_length=255)
    supplier = models.ForeignKey(CustomUser, on_delete=models.CASCADE, limit_choices_to={'role': 'supplier'})
    quantity = models.IntegerField()

    def __str__(self):
        return self.name

class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    from_user = models.ForeignKey(CustomUser, related_name='orders_from', on_delete=models.CASCADE)
    to_user = models.ForeignKey(CustomUser, related_name='orders_to', on_delete=models.CASCADE)
    transporter = models.CharField(max_length=255, blank=True)  # Assigned by stakeholder
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} - {self.product.name}"

class TransactionLog(models.Model):
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=255)
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    hash_value = models.CharField(max_length=64, editable=False)  # SHA-256
    prev_hash = models.CharField(max_length=64, blank=True, null=True, editable=False)

    class Meta:
        ordering = ['timestamp']
        unique_together = ['order', 'timestamp']

    def save(self, *args, **kwargs):
        # Get previous log
        previous_log = self.order.logs.exclude(pk=self.pk).order_by('-timestamp').first()
        self.prev_hash = previous_log.hash_value if previous_log else 'genesis'

        # Create data string
        data = f"{self.prev_hash}{self.action}{self.timestamp.isoformat()}{self.order.id}"
        self.hash_value = hashlib.sha256(data.encode()).hexdigest()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.timestamp.date()}] {self.action} by {self.user}"

    def verify_chain(self):
     """Verify entire hash chain from genesis to this log"""
     current = self
     while current:
        # Recompute expected hash
        prev = current.prev_hash or 'genesis'
        data = f"{prev}{current.action}{current.timestamp.isoformat()}{current.order.id}"
        expected = hashlib.sha256(data.encode()).hexdigest()

        if expected != current.hash_value:
            return False

        if prev == 'genesis':
            break

        # Get previous log
        try:
            current = current.order.logs.filter(timestamp__lt=current.timestamp).order_by('-timestamp')[0]
        except IndexError:
            break
     return True