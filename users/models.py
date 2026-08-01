from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import AbstractUser


class Organization(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.email or self.username


class Membership(models.Model):
    ROLE_CHOICES = [
        ('OWNER', 'Owner'),
        ('ADMIN', 'Admin'),
        ('MANAGER', 'Manager'),
        ('FINANCE', 'Finance'),
        ('MARKETING', 'Marketing'),
        ('SCANNER', 'Scanner'),
        ('VIEWER', 'Viewer'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='VIEWER')

    class Meta:
        unique_together = ('user', 'organization')  # Юзер не может быть в одной орг. дважды

    def __str__(self):
        # Для удобства в админке будет писать "username01 - Google (ADMIN)"
        return f"{self.user} - {self.organization.name} ({self.role})"