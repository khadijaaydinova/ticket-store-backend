from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import CustomUser, Organization, Membership

class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 1

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    inlines = [MembershipInline]

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    inlines = [MembershipInline]