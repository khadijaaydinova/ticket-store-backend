from django.db import models

# Create your models here.
import uuid # <--- Добавь это в самую верхнюю строчку файла к остальным импортам
import string
import random
from django.db import models
from users.models import Organization
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta


User = get_user_model()



class Event(models.Model):
    CATEGORY_CHOICES = [
        ('CONCERT', 'Konsert'),
        ('CONFERENCE', 'Konfrans'),
        ('SPORT', 'İdman'),
        ('THEATER', 'Teatr'),
        ('FESTIVAL', 'Festival'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    # НОВЫЕ ПОЛЯ ИЗ ТЗ:
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='CONCERT')
    city = models.CharField(max_length=100, default='Baku')  # Дефолтный город

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    location = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class TicketType(models.Model):
    # Валюты согласно требованиям (AZN, USD, EUR, TRY)
    CURRENCY_CHOICES = [
        ('AZN', 'Azerbaijani Manat'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('TRY', 'Turkish Lira'),
    ]

    # Тип рассадки для поддержки интерактивных карт залов
    SEATING_CHOICES = [
        ('GA', 'General Admission'),
        ('RESERVED', 'Reserved Seating'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticket_types')
    name = models.CharField(max_length=100)  # Например: "VIP", "Early Bird", "Student", "Group"

    # Блок цены
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='AZN')

    # Блок рассадки
    seating_type = models.CharField(max_length=15, choices=SEATING_CHOICES, default='GA')

    # Блок лимитов по количеству
    quantity_total = models.PositiveIntegerField(help_text="Общее количество билетов этого типа")
    quantity_sold = models.PositiveIntegerField(default=0, help_text="Сколько уже продано")

    # Блок ограничений на одну транзакцию (для групповых покупок и защиты от спекулянтов)
    min_per_order = models.PositiveIntegerField(default=1,
                                                help_text="Минимум билетов в одном заказе (например, 3 для Group)")
    max_per_order = models.PositiveIntegerField(default=10, help_text="Максимум билетов в одном заказе")

    # Период продаж (sales window)
    start_sale_date = models.DateTimeField(blank=True, null=True)
    end_sale_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.event.title} ({self.price} {self.currency})"

    @property
    def is_available(self):
        # Логика проверки, остались ли билеты в наличии
        return self.quantity_sold < self.quantity_total


class PromoCode(models.Model):
    DISCOUNT_TYPES = [
        ('PERCENT', 'Процент (%)'),
        ('FIXED', 'Фиксированная сумма'),
    ]

    code = models.CharField(max_length=20, unique=True, help_text="Сам промокод, например SUMMER20")
    # Если event не указан (null=True), промокод действует на ВСЕ мероприятия
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='promo_codes', null=True, blank=True)

    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default='PERCENT')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2,
                                         help_text="Размер скидки (например, 20 для 20%)")

    # Ограничения по времени и количеству
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    max_uses = models.PositiveIntegerField(null=True, blank=True,
                                           help_text="Максимальное количество использований (оставь пустым для безлимита)")
    times_used = models.PositiveIntegerField(default=0, help_text="Сколько раз уже применили")

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.discount_value} {self.discount_type})"

    @property
    def is_valid(self):
        """Умная проверка: активен ли код, не истек ли срок и не исчерпан ли лимит"""
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.valid_from or now > self.valid_to:
            return False
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False
        return True



class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Gözlənilir (Pending)'),
        ('PAID', 'Ödənilib (Paid)'),
        ('CANCELED', 'Ləğv edilib (Canceled)'),
    ]

    # Для гостевого чекаута временно разрешаем null, пока система не создаст пользователя под капотом
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    has_insurance = models.BooleanField(default=False, verbose_name="Страховка отмены")
    insurance_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Стоимость страховки")

    gift_card = models.ForeignKey('GiftCard', on_delete=models.SET_NULL, null=True, blank=True)
    gift_card_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # НОВЫЕ ПОЛЯ ДЛЯ СКИДКИ:
    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                          help_text="Сколько денег сэкономил клиент")
    final_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                      help_text="Сумма к оплате после скидки")

    def __str__(self):
        return f"Order #{self.id} - Status: {self.status}"



class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveIntegerField(default=1)

    # КРИТИЧЕСКИЙ ПАТТЕРН: Фиксируем цену на момент покупки
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    def __str__(self):
        return f"{self.quantity}x {self.ticket_type.name} (Order #{self.order.id})"

    def save(self, *args, **kwargs):
        # Автоматически сохраняем текущую цену типа билета при создании записи
        if not self.price_at_purchase:
            self.price_at_purchase = self.ticket_type.price
        super().save(*args, **kwargs)

#DAY 5
class Ticket(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tickets')
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name='tickets', null=True)
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    is_scanned = models.BooleanField(default=False)
    # НОВОЕ ПОЛЕ: Когда именно был просканирован билет.
    scanned_at = models.DateTimeField(null=True, blank=True)

    # ДОБАВЛЯЕМ ЭТУ СТРОЧКУ: Активен ли билет? (При отмене заказа будем менять на False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Ticket {self.code} - {self.ticket_type.name}"


# DAY 10
class ExchangeRate(models.Model):
    """
    Таблица для хранения курсов валют по отношению к базовой валюте (AZN).
    Например: 1 USD = 1.70 AZN.
    """
    currency = models.CharField(max_length=3, unique=True, help_text="Код валюты (например, USD, EUR, TRY)")
    exchange_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Сколько AZN стоит 1 единица этой валюты (Например, для USD введите 1.70)"
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="Когда курс обновлялся в последний раз")

    def __str__(self):
        return f"{self.currency} (1 {self.currency} = {self.exchange_rate} AZN)"


class ResaleListing(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Активно'),
        ('SOLD', 'Продано'),
        ('CANCELLED', 'Отменено'),
    ]

    # Если User у тебя импортируется из кастомной модели, убедись, что импорт правильный (например: from users.models import User)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resale_listings', verbose_name="Продавец")
    order_item = models.OneToOneField('OrderItem', on_delete=models.CASCADE, related_name='resale_listing', verbose_name="Билет")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена перепродажи")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата выставления")

    def __str__(self):
        return f"Ресейл #{self.id} | Билет #{self.order_item.id} за {self.price} AZN ({self.get_status_display()})"


class MembershipPlan(models.Model):
    INTERVAL_CHOICES = (
        ('MONTHLY', 'Aylıq (Monthly)'),
        ('YEARLY', 'İllik (Yearly)'),
    )

    name = models.CharField(max_length=100, verbose_name="План подписки")
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='MONTHLY')
    discount_percentage = models.PositiveIntegerField(default=0, help_text="Скидка на билеты в % (например, 15)")
    free_tickets_count = models.PositiveIntegerField(default=0, help_text="Кол-во бесплатных билетов в период")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.price} AZN / {self.interval})"


class UserSubscription(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT, related_name='user_subscriptions')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Автоматический расчет end_date при создании
        if not self.end_date:
            days = 365 if self.plan.interval == 'YEARLY' else 30
            self.end_date = timezone.now() + timedelta(days=days)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.status == 'ACTIVE' and self.end_date >= timezone.now()

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"


# Функция для генерации красивого кода (например: A7X9-P2M4-K8J1)
def generate_gift_card_code():
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    return f"{chars[:4]}-{chars[4:8]}-{chars[8:]}"

class GiftCard(models.Model):
    code = models.CharField(max_length=14, unique=True, default=generate_gift_card_code)
    initial_balance = models.DecimalField(max_digits=10, decimal_places=2)
    current_balance = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"GiftCard {self.code} | Balance: {self.current_balance}"