import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import render
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiParameter

# --- Локальные импорты проекта ---
from .models import (
    Event, Order, Ticket, OrderItem, TicketType, PromoCode,
    ResaleListing, MembershipPlan, UserSubscription, GiftCard
)
from .serializers import (
    EventSerializer,
    OrderSerializer,
    TicketSerializer,
    ScanTicketSerializer,
    CheckoutSerializer,
    CheckoutResponseSerializer,
    ResaleListingSerializer,
    MembershipPlanSerializer,
    UserSubscriptionSerializer,
    SubscribeRequestSerializer
)
from .permissions import IsScannerOrAdmin
from .utils import generate_ticket_pdf

User = get_user_model()


class MembershipViewSet(viewsets.ModelViewSet):
    queryset = MembershipPlan.objects.filter(is_active=True)
    serializer_class = MembershipPlanSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @action(detail=False, methods=['post'], url_path='subscribe', permission_classes=[permissions.IsAuthenticated])
    def subscribe(self, request):
        """
        Оформить или обновить подписку: POST /api/memberships/subscribe/
        Body: {"plan_id": 1}
        """
        serializer = SubscribeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_id = serializer.validated_data['plan_id']
        try:
            plan = MembershipPlan.objects.get(id=plan_id, is_active=True)
        except MembershipPlan.DoesNotExist:
            return Response({"error": "Указанный план подписки не найден или неактивен."}, status=status.HTTP_404_NOT_FOUND)

        # Проверяем, нет ли уже активной подписки
        active_sub = UserSubscription.objects.filter(
            user=request.user,
            status='ACTIVE',
            end_date__gte=timezone.now()
        ).first()

        if active_sub:
            # Продлеваем действующую подписку или меняем план
            active_sub.plan = plan
            days = 365 if plan.interval == 'YEARLY' else 30
            active_sub.end_date = timezone.now() + timedelta(days=days)
            active_sub.save()
            return Response({
                "message": f"Ваша подписка успешно обновлена на '{plan.name}'!",
                "subscription": UserSubscriptionSerializer(active_sub).data
            }, status=status.HTTP_200_OK)

        # Создаем новую подписку
        subscription = UserSubscription.objects.create(
            user=request.user,
            plan=plan,
            status='ACTIVE'
        )

        return Response({
            "message": f"Вы успешно подписались на план '{plan.name}'!",
            "subscription": UserSubscriptionSerializer(subscription).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='my-subscription', permission_classes=[permissions.IsAuthenticated])
    def my_subscription(self, request):
        """
        Получить статус текущей подписки пользователя: GET /api/memberships/my-subscription/
        """
        sub = UserSubscription.objects.filter(
            user=request.user,
            status='ACTIVE',
            end_date__gte=timezone.now()
        ).first()

        if not sub:
            return Response({"message": "У вас нет активной подписки.", "has_active_subscription": False}, status=status.HTTP_200_OK)

        return Response({
            "has_active_subscription": True,
            "subscription": UserSubscriptionSerializer(sub).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='cancel', permission_classes=[permissions.IsAuthenticated])
    def cancel_subscription(self, request):
        """
        Отменить автопродление подписки: POST /api/memberships/cancel/
        """
        sub = UserSubscription.objects.filter(user=request.user, status='ACTIVE').first()
        if not sub:
            return Response({"error": "Активная подписка не найдена."}, status=status.HTTP_404_NOT_FOUND)

        sub.auto_renew = False
        sub.status = 'CANCELLED'
        sub.save()

        return Response({"message": "Автопродление подписки успешно отменено.", "subscription": UserSubscriptionSerializer(sub).data}, status=status.HTTP_200_OK)


class ResaleViewSet(viewsets.ModelViewSet):
    queryset = ResaleListing.objects.filter(status='ACTIVE')
    serializer_class = ResaleListingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def cancel(self, request, pk=None):
        listing = self.get_object()

        # 1. Проверяем, что отменить пытается именно владелец билета
        if listing.seller != request.user:
            return Response(
                {"error": "Вы не можете снять с продажи чужой билет!"},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Проверяем, активен ли статус
        if listing.status != 'ACTIVE':
            return Response(
                {"error": "Можно отменить только активные объявления (ACTIVE)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Меняем статус на отмененный
        listing.status = 'CANCELLED'
        listing.save()

        return Response(
            {"message": "Объявление успешно снято с продажи. Билет снова доступен для использования!"},
            status=status.HTTP_200_OK
        )

    def create(self, request, *args, **kwargs):
        order_item_id = request.data.get('order_item')

        try:
            # Проверяем, существует ли такой билет и принадлежит ли он юзеру
            order_item = OrderItem.objects.get(id=order_item_id, order__user=request.user)
        except OrderItem.DoesNotExist:
            return Response(
                {"error": "Билет не найден или не принадлежит вам."},
                status=status.HTTP_404_NOT_FOUND
            )

        # БЕЗОПАСНОСТЬ: Проверяем статус сканирования
        scanned_tickets = Ticket.objects.filter(
            order=order_item.order,
            ticket_type=order_item.ticket_type,
            is_scanned=True
        ).count()

        total_tickets = Ticket.objects.filter(
            order=order_item.order,
            ticket_type=order_item.ticket_type
        ).count()

        active_resales = ResaleListing.objects.filter(
            order_item__order=order_item.order,
            order_item__ticket_type=order_item.ticket_type,
            status='ACTIVE'
        ).count()

        # Если доступных (не отсканированных и не выставленных на продажу) билетов больше нет:
        if (total_tickets - scanned_tickets - active_resales) <= 0:
            return Response(
                {"error": "Ошибка безопасности: Этот билет уже отсканирован на входе или выставлен на продажу!"},
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def buy(self, request, pk=None):
        listing = self.get_object()

        if listing.status != 'ACTIVE':
            return Response({"error": "Этот билет уже продан или снят с продажи."}, status=status.HTTP_400_BAD_REQUEST)

        if listing.seller == request.user:
            return Response({"error": "Вы не можете купить свой собственный билет!"},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            listing.status = 'SOLD'
            listing.save()

            platform_fee = listing.price * Decimal('0.10')
            total_price = listing.price + platform_fee

            new_order = Order.objects.create(
                user=request.user,
                total_price=total_price,
                final_price=total_price,
                status='PAID'
            )

            old_item = listing.order_item

            new_item = OrderItem.objects.create(
                order=new_order,
                ticket_type=old_item.ticket_type,
                quantity=1,
                price_at_purchase=listing.price
            )

            # Находим билет продавца и передаем его покупателю с НОВЫМ кодом
            ticket = Ticket.objects.filter(
                order=old_item.order,
                ticket_type=old_item.ticket_type,
                is_scanned=False,
                is_active=True
            ).first()

            if ticket:
                ticket.order = new_order  # Передаем билет новому владельцу
                ticket.code = uuid.uuid4()  # Аннулируем старый QR-код и создаем новый!
                ticket.save()
            else:
                ticket = Ticket.objects.create(
                    order=new_order,
                    ticket_type=old_item.ticket_type,
                    is_scanned=False,
                    is_active=True
                )

            old_item.quantity = 0
            old_item.save()

            return Response({
                "message": "Успешно куплено!",
                "new_order_id": new_order.id,
                "ticket_code": str(ticket.code),
                "total_paid": str(total_price),
                "platform_fee": str(platform_fee)
            }, status=status.HTTP_201_CREATED)


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['city', 'category']
    search_fields = ['title', 'description']
    ordering_fields = ['start_date', 'created_at']

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='currency',
                description='Код валюты для конвертации цен билетов (например: USD, EUR, TRY)',
                required=False,
                type=str
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class TicketViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Ticket.objects.filter(order__user=self.request.user)

    @extend_schema(summary="Скачать PDF-билет с QR-кодом")
    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        ticket = self.get_object()
        pdf_buffer = generate_ticket_pdf(ticket)
        return FileResponse(
            pdf_buffer,
            as_attachment=True,
            filename=f"ticket_{ticket.code}.pdf"
        )


class ScanTicketView(APIView):
    permission_classes = [IsScannerOrAdmin]

    @extend_schema(
        request=ScanTicketSerializer,
        summary="Сканирование билета на входе",
        description="Проверяет UUID билета и отмечает его как использованный."
    )
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "You are not logged in!"}, status=status.HTTP_401_UNAUTHORIZED)

        if not request.user.is_superuser and not request.user.membership_set.filter(
                role__in=['SCANNER', 'ADMIN', 'OWNER']).exists():
            return Response({"error": "You are not a scanner!"}, status=status.HTTP_403_FORBIDDEN)

        provided_code = request.data.get('code')
        if not provided_code:
            return Response({"error": "Please provide a ticket code."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ticket = Ticket.objects.get(code=provided_code)
        except Ticket.DoesNotExist:
            return Response({"error": "Invalid or fake ticket."}, status=status.HTTP_404_NOT_FOUND)

        if not ticket.is_active:
            return Response({"error": "This ticket has been cancelled or refunded!"}, status=status.HTTP_400_BAD_REQUEST)

        if ticket.is_scanned:
            return Response({
                "error": "Ticket has already been scanned!",
                "scanned_at": ticket.scanned_at
            }, status=status.HTTP_400_BAD_REQUEST)

        ticket.is_scanned = True
        ticket.scanned_at = timezone.now()
        ticket.save()

        return Response({
            "message": "Access granted! Welcome to the event.",
            "ticket_category": ticket.ticket_type.name
        }, status=status.HTTP_200_OK)


class OrderViewSet(viewsets.ModelViewSet):

    def get_queryset(self):
        """ЗАЩИТА ОТ IDOR: Пользователь видит только свои собственные заказы."""
        if getattr(self, 'swagger_fake_view', False):
            return Order.objects.none()

        if self.request.user.is_authenticated:
            return Order.objects.filter(user=self.request.user)
        return Order.objects.none()

    @action(detail=False, methods=['get'], url_path='my-tickets')
    def my_tickets(self, request):
        """
        Возвращает список всех позиций (OrderItem) и билетов текущего пользователя
        с явным указанием order_item_id для перепродажи.
        """
        if not request.user.is_authenticated:
            return Response({"error": "Требуется авторизация"}, status=status.HTTP_401_UNAUTHORIZED)

        order_items = OrderItem.objects.filter(
            order__user=request.user
        ).select_related('ticket_type', 'ticket_type__event', 'order')

        data = []
        for item in order_items:
            ticket = Ticket.objects.filter(order=item.order, ticket_type=item.ticket_type).first()
            is_on_resale = hasattr(item, 'resale_listing') and item.resale_listing.status == 'ACTIVE'

            data.append({
                "order_item_id": item.id,
                "order_id": item.order.id,
                "event_title": item.ticket_type.event.title if item.ticket_type and item.ticket_type.event else "N/A",
                "ticket_type": item.ticket_type.name if item.ticket_type else "N/A",
                "price_paid": str(item.price_at_purchase),
                "ticket_code": str(ticket.code) if ticket else None,
                "is_scanned": ticket.is_scanned if ticket else False,
                "is_active": ticket.is_active if ticket else False,
                "is_on_resale": is_on_resale
            })

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='refund', permission_classes=[permissions.IsAuthenticated])
    def refund_order(self, request, pk=None):
        """
        Эндпоинт возврата заказа: POST /api/orders/{id}/refund/
        Проверяет наличие страховки и деактивирует билеты.
        """
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"error": "Заказ не найден или у вас нет прав на его возврат."},
                status=status.HTTP_404_NOT_FOUND
            )

        if order.status == 'REFUNDED':
            return Response(
                {"error": "Этот заказ уже был успешно возвращен ранее."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if order.status == 'CANCELLED':
            return Response(
                {"error": "Нельзя оформить возврат для отмененного заказа."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not order.has_insurance:
            return Response(
                {
                    "error": "Возврат отклонен",
                    "reason": "Заказ был оформлен без страховки от отмены (Refund Insurance).",
                    "has_insurance": False
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            order.status = 'REFUNDED'
            order.save()

            # Деактивируем все билеты, связанные с этим заказом
            tickets = Ticket.objects.filter(order=order)
            tickets_updated_count = tickets.update(is_active=False)

            refund_amount = order.final_price - order.insurance_fee

        return Response(
            {
                "message": "Заказ успешно возвращен! Деньги отправлены на ваш счет.",
                "order_id": order.id,
                "status": order.status,
                "refunded_amount": f"{refund_amount:.2f}",
                "retained_insurance_fee": f"{order.insurance_fee:.2f}",
                "cancelled_tickets_count": tickets_updated_count
            },
            status=status.HTTP_200_OK
        )

    @extend_schema(
        request=CheckoutSerializer,
        summary="Оформление заказа (Guest Checkout)",
        description="Генерация билетов, промокоды, подарочные карты и опциональная страховка."
    )
    @action(detail=False, methods=['post'], permission_classes=[])
    def checkout(self, request):
        items = request.data.get('items')
        promo_code_str = request.data.get('promo_code', None)
        add_insurance = request.data.get('add_insurance', False)
        gift_card_code = request.data.get('gift_card_code', None)  # <-- Получаем код карты из запроса

        if not items or not isinstance(items, list):
            return Response({"error": "Корзина пуста или неверный формат items"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 1. Создаем "пустой" заказ (цены обновим в конце)
                order = Order.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    total_price=0,
                    final_price=0,
                    status='PAID'
                )

                total_price = Decimal('0.00')
                tickets_generated = 0

                # 2. Считаем стоимость билетов и создаем их в базе
                for item in items:
                    ticket_type_id = item.get('ticket_type_id')
                    quantity = int(item.get('quantity', 1))

                    if not ticket_type_id:
                        raise ValueError("Укажите ticket_type_id для каждого товара в items")

                    ticket_type = TicketType.objects.get(id=ticket_type_id)

                    if not ticket_type.is_available:
                        raise ValueError(f"Билеты типа '{ticket_type.name}' закончились")

                    item_total = ticket_type.price * quantity
                    total_price += item_total

                    for _ in range(quantity):
                        OrderItem.objects.create(
                            order=order,
                            ticket_type=ticket_type,
                            quantity=1,
                            price_at_purchase=ticket_type.price
                        )

                        Ticket.objects.create(
                            order=order,
                            ticket_type=ticket_type,
                            is_scanned=False,
                            is_active=True
                        )
                        tickets_generated += 1

                    ticket_type.quantity_sold += quantity
                    ticket_type.save()

                # 3. Применяем промокод (если есть)
                discount_amount = Decimal('0.00')
                if promo_code_str:
                    try:
                        promo = PromoCode.objects.get(code=promo_code_str)
                        if promo.is_valid:
                            if promo.discount_type == 'PERCENT':
                                discount_amount = (total_price * promo.discount_value) / Decimal('100')
                            elif promo.discount_type == 'FIXED':
                                discount_amount = promo.discount_value

                            promo.times_used += 1
                            promo.save()
                            order.promo_code = promo
                    except PromoCode.DoesNotExist:
                        pass

                # 4. Считаем страховку (если выбрана)
                insurance_fee = Decimal('0.00')
                if add_insurance:
                    insurance_fee = total_price * Decimal('0.07')
                    order.has_insurance = True
                    order.insurance_fee = insurance_fee

                # 5. Считаем промежуточную цену (до подарочной карты)
                final_price = max(Decimal('0.00'), total_price - discount_amount) + insurance_fee

                # 6. --- БЛОК GIFT CARD ---
                gift_card_discount = Decimal('0.00')
                if gift_card_code:
                    try:
                        gift_card_obj = GiftCard.objects.get(code=gift_card_code, is_active=True)

                        if gift_card_obj.current_balance > 0:
                            if gift_card_obj.current_balance >= final_price:
                                gift_card_discount = final_price
                                gift_card_obj.current_balance -= final_price
                                final_price = Decimal('0.00')
                            else:
                                gift_card_discount = gift_card_obj.current_balance
                                final_price -= gift_card_obj.current_balance
                                gift_card_obj.current_balance = Decimal('0.00')

                            gift_card_obj.save()
                            order.gift_card = gift_card_obj
                            order.gift_card_discount = gift_card_discount
                        else:
                            raise ValueError("Баланс подарочной карты равен 0")

                    except GiftCard.DoesNotExist:
                        raise ValueError("Неверная или неактивная подарочная карта")
                # --- КОНЕЦ БЛОКА GIFT CARD ---

                # 7. Обновляем итоговые цифры в заказе и сохраняем его
                order.total_price = total_price
                order.discount_amount = discount_amount
                order.final_price = final_price
                order.save()

            # Если мы дошли сюда, транзакция успешно завершена!
            return Response({
                "message": "Заказ успешно оформлен!",
                "order_id": order.id,
                "total_price": str(order.total_price),
                "discount_amount": str(order.discount_amount),
                "insurance_fee": str(order.insurance_fee),
                "gift_card_discount": str(gift_card_discount) if gift_card_code else "0.00",
                "final_price": str(order.final_price),
                "tickets_generated": tickets_generated
            }, status=status.HTTP_201_CREATED)

        except TicketType.DoesNotExist:
            return Response({"error": "Один из типов билетов не найден"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            # Сюда прилетят ошибки про закончившиеся билеты или пустые подарочные карты
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Внутренняя ошибка: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)