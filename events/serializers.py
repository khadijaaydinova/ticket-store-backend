from rest_framework import serializers
from django.db import transaction # <--- ДОБАВИТЬ ЭТО
from .models import Event, TicketType, Order, OrderItem, Ticket # Не забудь добавить Ticket в импорты наверху!
from .models import ExchangeRate
from decimal import Decimal # Убедись, что Decimal импортирован
from .models import ResaleListing, OrderItem # Добавь ResaleListing в импорты
from .models import Speaker, AgendaSession, AttendeeSchedule
from .models import AbstractSubmission, Sponsor
from .models import QAQuestion, LivePoll, PollOption, PollVote



#
# # 1. Сначала описываем, как переводить в JSON билеты
# class TicketTypeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = TicketType
#         # Строго перечисляем только те поля, которые реально есть в новой модели!
#         fields = [
#             'id',
#             'name',
#             'price',
#             'currency',
#             'seating_type',
#             'quantity_total',
#             'quantity_sold',
#             'min_per_order',
#             'max_per_order',
#             'start_sale_date',
#             'end_sale_date',
#             'is_available' # Это наше вычисляемое @property из модели
#         ]

class TicketTypeSerializer(serializers.ModelSerializer):
    # Добавляем два виртуальных поля, которых нет в базе данных, но они будут в JSON
    converted_price = serializers.SerializerMethodField(help_text="Цена в запрошенной валюте")
    requested_currency = serializers.SerializerMethodField(help_text="Запрошенная валюта (по умолчанию AZN)")

    class Meta:
        model = TicketType
        fields = [
            'id', 'name', 'price', 'converted_price', 'requested_currency',
            'quantity_total', 'quantity_sold', 'min_per_order', 'max_per_order'
        ]

    def get_requested_currency(self, obj):
        # Достаем request из контекста сериализатора
        request = self.context.get('request')
        if request:
            # Ищем параметр ?currency= в URL. Если его нет, по умолчанию берем AZN
            return request.query_params.get('currency', 'AZN').upper()
        return 'AZN'

    def get_converted_price(self, obj):
        request = self.context.get('request')
        target_currency = 'AZN'

        if request:
            target_currency = request.query_params.get('currency', 'AZN').upper()

        # Если запросили базовую валюту, возвращаем оригинальную цену из базы
        if target_currency == 'AZN':
            return obj.price

        # Если запросили другую валюту (например, USD), ищем курс в базе
        try:
            rate_obj = ExchangeRate.objects.get(currency=target_currency)
            # Математика: 100 AZN / 1.70 = 58.82 USD
            converted = obj.price / rate_obj.exchange_rate
            return round(converted, 2)
        except ExchangeRate.DoesNotExist:
            # Если такого курса в базе нет (или забыли добавить), отдаем в AZN как fallback (защита от ошибок)
            return obj.price

# 2. Затем описываем само мероприятие
class EventSerializer(serializers.ModelSerializer):
    # Магия вложенности: мы говорим, что поле ticket_types
    # должно обрабатываться нашим TicketTypeSerializer'ом
    ticket_types = TicketTypeSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        # Обязательно добавляем 'ticket_types' в список полей
        fields = [
            'id',
            'organization',
            'organization_name',
            'title',
            'description',
            'category',
            'city',
            'start_date',
            'end_date',
            'location',
            'ticket_types'  # <--- Вот оно!
        ]

    # Делаем так, чтобы отдавалось название организации, а не просто её цифра-ID
    organization_name = serializers.CharField(source='organization.name', read_only=True)




#DAY 4

# Сериализатор для отдельного билетика в корзине
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['ticket_type', 'quantity']
        # Обрати внимание: цену (price) мы от пользователя не ждем!
        # Иначе хитрый хакер пришлет нам JSON: "Хочу VIP билет за 0 рублей".
        # Цену мы будем брать строго из нашей базы данных.


# Сериализатор для всего заказа
class OrderSerializer(serializers.ModelSerializer):
    # Говорим, что внутри заказа лежит список билетов (матрешка)
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'event', 'status', 'total_price', 'created_at', 'items']
        # Эти поля пользователь не может менять руками, мы считаем их сами:
        read_only_fields = ['status', 'total_price', 'created_at']

    # Переопределяем стандартный метод создания (Тот самый мозг, который ты описал)
    def create(self, validated_data):
        # 1. Достаем список билетов из JSON
        items_data = validated_data.pop('items')

        # Узнаем, кто делает запрос (достаем юзера из JWT-токена)
        user = self.context['request'].user

        total_price = 0

        # 2. ОТКРЫВАЕМ ТРАНЗАКЦИЮ! (Невидимый купол)
        with transaction.atomic():

            # 3. Создаем "пустой" бланк заказа в базе
            order = Order.objects.create(user=user, **validated_data)

            # 4. Проходимся по каждому билету, который запросил покупатель
            for item_data in items_data:
                ticket_type = item_data['ticket_type']
                quantity_requested = item_data['quantity']

                # ШАГ А: Проверка склада
                if ticket_type.quantity < quantity_requested:
                    # Если билетов нет, мы "взрываем" код ошибкой.
                    # Из-за transaction.atomic() весь заказ мгновенно отменится.
                    raise serializers.ValidationError(
                        f"Недостаточно билетов категории {ticket_type.name}. Осталось: {ticket_type.quantity}"
                    )

                # ШАГ Б: Списание со склада (бронируем билеты)
                ticket_type.quantity -= quantity_requested
                ticket_type.save()

                # ШАГ В: Калькуляция и фиксация цены
                price_at_purchase = ticket_type.price
                total_price += (price_at_purchase * quantity_requested)

                # ШАГ Г: Привязываем билет к заказу
                OrderItem.objects.create(
                    order=order,
                    ticket_type=ticket_type,
                    quantity=quantity_requested,
                    price_at_purchase=price_at_purchase
                )

            # 5. Обновляем итоговую цену всего заказа и сохраняем
            order.total_price = total_price
            order.save()

        # Транзакция закрылась. Возвращаем готовый заказ,
        # чтобы Django превратил его обратно в JSON и отдал юзеру.
        return order


class TicketSerializer(serializers.ModelSerializer):
    # Достаем названия, чтобы фронтенду было удобно рисовать билет
    event_title = serializers.CharField(source='order.event.title', read_only=True)
    ticket_category = serializers.CharField(source='ticket_type.name', read_only=True)

    class Meta:
        model = Ticket
        fields = ['id', 'code', 'event_title', 'ticket_category', 'is_scanned']


#DAY 6

class ScanTicketSerializer(serializers.Serializer):
    code = serializers.UUIDField(help_text="Введите UUID код билета для сканирования")

#DAY 8
class CheckoutItemSerializer(serializers.Serializer):
    ticket_type_id = serializers.IntegerField(help_text="ID типа билета (например, 1 для VIP)")
    quantity = serializers.IntegerField(min_value=1, help_text="Количество билетов")


class CheckoutSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Email покупателя (для гостевого чекаута)")
    first_name = serializers.CharField(max_length=100, help_text="Имя")
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True, help_text="Фамилия")

    # НОВОЕ ПОЛЕ:
    promo_code = serializers.CharField(max_length=20, required=False, allow_blank=True,
                                       help_text="Промокод (необязательно)")
    # Вложенный список покупаемых билетов
    items = CheckoutItemSerializer(many=True, help_text="Список покупаемых билетов")

# events/serializers.py
class CheckoutResponseSerializer(serializers.Serializer):
    message = serializers.CharField(help_text="Сообщение об успешном статусе")
    order_id = serializers.IntegerField(help_text="ID созданного заказа")
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Исходная сумма")
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Сумма скидки")
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Финальная сумма к оплате")
    status = serializers.CharField(help_text="Статус заказа (например, PAID)")
    tickets_generated = serializers.IntegerField(help_text="Количество выпущенных билетов")


#DAY 10

class ResaleListingSerializer(serializers.ModelSerializer):
    seller_email = serializers.CharField(source='seller.email', read_only=True)
    ticket_name = serializers.CharField(source='order_item.ticket_type.name', read_only=True)
    event_title = serializers.CharField(source='order_item.ticket_type.event.title', read_only=True)

    class Meta:
        model = ResaleListing
        fields = ['id', 'seller_email', 'order_item', 'event_title', 'ticket_name', 'price', 'status', 'created_at']
        read_only_fields = ['status', 'seller']

    def validate_price(self, value):
        order_item_id = self.initial_data.get('order_item')
        if order_item_id:
            try:
                item = OrderItem.objects.get(id=order_item_id)
                original_price = item.price_at_purchase
                max_allowed_price = original_price * Decimal('1.10')

                if value > max_allowed_price:
                    raise serializers.ValidationError(
                        f"Максимальная цена продажи не может превышать {max_allowed_price} AZN (+10% от номинала)."
                    )
            except OrderItem.DoesNotExist:
                pass
        return value

from rest_framework import serializers
from .models import MembershipPlan, UserSubscription

class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = ['id', 'name', 'description', 'price', 'interval', 'discount_percentage', 'free_tickets_count', 'is_active']


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_details = MembershipPlanSerializer(source='plan', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserSubscription
        fields = ['id', 'plan', 'plan_details', 'status', 'start_date', 'end_date', 'auto_renew', 'is_valid', 'created_at']
        read_only_fields = ['status', 'start_date', 'end_date', 'created_at']


class SubscribeRequestSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(required=True)

class SpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Speaker
        fields = '__all__'

class AgendaSessionSerializer(serializers.ModelSerializer):
    # Добавляем вложенный сериализатор, чтобы при запросе расписания
    # мы сразу видели детальную инфу о спикерах, а не просто их ID
    speaker_details = SpeakerSerializer(source='speakers', many=True, read_only=True)

    class Meta:
        model = AgendaSession
        fields = '__all__'

class AttendeeScheduleSerializer(serializers.ModelSerializer):
    session_details = AgendaSessionSerializer(source='session', read_only=True)

    class Meta:
        model = AttendeeSchedule
        fields = ['id', 'session', 'session_details', 'added_at']
        read_only_fields = ['user']

class SponsorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sponsor
        fields = '__all__'

class AbstractSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AbstractSubmission
        fields = '__all__'
        # БЕЗОПАСНОСТЬ: запрещаем юзеру самому передавать статус и подменять автора!
        read_only_fields = ['applicant', 'status', 'submitted_at']

class QAQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QAQuestion
        fields = '__all__'
        # БЕЗОПАСНОСТЬ: запрещаем юзеру подменять автора, статусы и накручивать лайки вручную
        read_only_fields = ['user', 'upvotes', 'is_answered', 'created_at']

class PollOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PollOption
        fields = ['id', 'text']

class LivePollSerializer(serializers.ModelSerializer):
    # Вкладываем варианты ответа прямо в опрос, чтобы фронтенду было удобно их рендерить
    options = PollOptionSerializer(many=True, read_only=True)

    class Meta:
        model = LivePoll
        fields = '__all__'