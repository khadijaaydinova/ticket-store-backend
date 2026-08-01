from rest_framework import serializers
from .models import Organization

class OrganizationSerializer(serializers.ModelSerializer):
    # Добавляем обратную связь.
    # StringRelatedField выведет результат метода __str__ пользователя (email или username)
    members = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Organization
        # Не забываем добавить 'members' в список возвращаемых полей
        fields = ['id', 'name', 'created_at', 'members']