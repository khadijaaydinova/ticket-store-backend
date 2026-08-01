from rest_framework import permissions
from .models import Membership


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Кастомное правило: разрешает редактирование только владельцам или админам.
    """

    # Этот метод автоматически вызывается, когда кто-то пытается обратиться к конкретной Организации
    def has_object_permission(self, request, view, obj):
        # SAFE_METHODS — это безопасные запросы на чтение (GET, HEAD, OPTIONS).
        # Мы разрешаем просто "смотреть" на организацию всем.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Если запрос пытается изменить данные (PUT, PATCH, DELETE) или создать:
        # 1. Проверяем, авторизован ли пользователь вообще
        if not request.user or not request.user.is_authenticated:
            return False

        # 2. Делаем запрос в базу данных: ищем запись в таблице Membership,
        # где user — это тот, кто делает запрос, organization — это текущая организация,
        # а роль — либо OWNER, либо ADMIN.
        # .exists() вернет True, если такая запись есть, и False, если нет.
        return Membership.objects.filter(
            user=request.user,
            organization=obj,
            role__in=['OWNER', 'ADMIN']
        ).exists()