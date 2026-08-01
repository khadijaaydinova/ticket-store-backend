from rest_framework import permissions
from users.models import Membership  # Импортируем твою модель Membership


class IsScannerOrAdmin(permissions.BasePermission):
    """
    Разрешает доступ только суперюзерам или пользователям
    с ролью SCANNER / ADMIN в любой из организаций.
    """

    def has_permission(self, request, view):
        # 1. Сначала базовая проверка: человек вообще авторизован?
        if not request.user or not request.user.is_authenticated:
            return False

        # 2. Если это главный админ сайта (is_superuser), пускаем его всегда
        if request.user.is_superuser:
            return True

        # 3. Ищем пользователя в таблице Membership с нужными ролями.
        # (Убедись, что названия ролей совпадают с теми, что ты писал в моделях users,
        # если там было с маленькой буквы, например 'scanner', то поменяй здесь).
        has_role = Membership.objects.filter(
            user=request.user,
            role__in=['SCANNER', 'ADMIN', 'OWNER']
        ).exists()

        return has_role