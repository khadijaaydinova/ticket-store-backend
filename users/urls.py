from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrganizationViewSet

# Роутер автоматически создаст пути для всех CRUD операций (/organizations/, /organizations/1/)
router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]