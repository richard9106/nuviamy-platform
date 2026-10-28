from django.conf import settings
from django.db import models
import uuid

from apps.practices.models import Practice
from .fields import SupportEncryptedTextField


class SupportTicket(models.Model):
    class Topic(models.TextChoices):
        SETUP = 'setup', 'Practice setup'
        BILLING = 'billing', 'Billing or payments'
        INTEGRATIONS = 'integrations', 'Google Calendar or Stripe'
        TECHNICAL = 'technical', 'Technical issue'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        CLOSED = 'closed', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.PROTECT, related_name='support_tickets')
    practice = models.ForeignKey(Practice, null=True, blank=True, on_delete=models.PROTECT)
    contact_name = SupportEncryptedTextField(blank=True)
    contact_email = SupportEncryptedTextField()
    topic = models.CharField(max_length=20, choices=Topic.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Support request {self.pk}'


class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.PROTECT, related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    is_operator = models.BooleanField(default=False)
    body = SupportEncryptedTextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'Support message {self.pk}'


class Customer(models.Model):
    name = models.CharField(max_length=140)
    email = models.EmailField(unique=True)
    segment = models.CharField(max_length=60, default='standard')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=140)
    sku = models.CharField(max_length=40, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Sale(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='sales')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='sales')
    quantity = models.PositiveIntegerField(default=1)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    sold_at = models.DateTimeField()

    class Meta:
        ordering = ['-sold_at']


class OperationalEvent(models.Model):
    class Level(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'

    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In progress'
        DONE = 'done', 'Done'

    practice = models.ForeignKey(Practice, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assigned_nuvia_tasks')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_nuvia_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'due_date', '-created_at']
        indexes = [models.Index(fields=['practice', 'status', 'due_date'])]

    def __str__(self):
        return self.title
