from django.contrib import admin
from .models import Event, TicketType, PromoCode, Order, OrderItem, Ticket, ExchangeRate, ResaleListing, GiftCard, LivePoll, PollOption, PollVote

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'category', 'city', 'start_date', 'end_date')
    list_filter = ('category', 'city', 'organization')
    search_fields = ('title', 'description')

@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'price', 'currency', 'quantity_total', 'quantity_sold')
    list_filter = ('currency', 'seating_type', 'event')
    search_fields = ('name', 'event__title')

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'total_price', 'discount_amount', 'final_price', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user__email', 'user__username')
    inlines = [OrderItemInline]

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_buyer', 'ticket_type', 'quantity', 'price_at_purchase', 'order')
    list_filter = ('ticket_type__event', 'ticket_type')
    search_fields = ('id', 'order__user__email', 'order__user__username')

    @admin.display(description='Покупатель (Email)')
    def get_buyer(self, obj):
        return obj.order.user.email if obj.order and obj.order.user else "Гость"


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    # Выводим UUID билета, Email владельца, название мероприятия и статус сканирования
    list_display = ('code', 'get_owner', 'get_event', 'ticket_type', 'is_scanned', 'scanned_at')
    list_filter = ('is_scanned', 'ticket_type__event')
    search_fields = ('code', 'order__user__email', 'order__user__username')

    @admin.display(description='Владелец (Email)')
    def get_owner(self, obj):
        return obj.order.user.email if obj.order and obj.order.user else "Гость"

    @admin.display(description='Мероприятие')
    def get_event(self, obj):
        return obj.ticket_type.event.title if obj.ticket_type and obj.ticket_type.event else "-"

@admin.register(ResaleListing)
class ResaleListingAdmin(admin.ModelAdmin):
    list_display = ('id', 'seller', 'order_item', 'price', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('seller__email', 'seller__username')

admin.site.register(PromoCode)
admin.site.register(ExchangeRate)

@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = ('code', 'initial_balance', 'current_balance', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code',)
    readonly_fields = ('created_at',)


class PollOptionInline(admin.TabularInline):
    model = PollOption
    extra = 2 # Будет показывать сразу 2 пустых поля для ответов (например, "Да" и "Нет")

@admin.register(LivePoll)
class LivePollAdmin(admin.ModelAdmin):
    list_display = ('question', 'event', 'is_active', 'created_at')
    list_filter = ('is_active', 'event')
    inlines = [PollOptionInline]

@admin.register(PollVote)
class PollVoteAdmin(admin.ModelAdmin):
    list_display = ('poll', 'option', 'user')
    list_filter = ('poll',)

# from django.contrib import admin
# from .models import Event, TicketType, ExchangeRate, PromoCode, Order, OrderItem, ResaleListing
#
# @admin.register(ExchangeRate)
# class ExchangeRateAdmin(admin.ModelAdmin):
#     list_display = ('currency', 'exchange_rate', 'updated_at')
#
# @admin.register(PromoCode)
# class PromoCodeAdmin(admin.ModelAdmin):
#     list_display = ('code', 'discount_type', 'discount_value', 'valid_from', 'valid_to', 'times_used', 'max_uses', 'is_active')
#     list_filter = ('is_active', 'discount_type')
#     search_fields = ('code',)
#
# class TicketTypeInline(admin.TabularInline):
#     model = TicketType
#     extra = 1
#
# @admin.register(Event)
# class EventAdmin(admin.ModelAdmin):
#     list_display = ('title', 'organization', 'start_date', 'location')
#     list_filter = ('organization', 'start_date')
#     inlines = [TicketTypeInline]
#
# @admin.register(TicketType)
# class TicketTypeAdmin(admin.ModelAdmin):
#     list_display = ('name', 'event', 'price', 'currency', 'seating_type', 'quantity_sold', 'quantity_total')
#     list_filter = ('currency', 'seating_type')
#     search_fields = ('name', 'event__title')
#
# # Регистрируем оставшиеся модели через декораторы или обычным методом (но ровно по 1 разу!)
# @admin.register(Order)
# class OrderAdmin(admin.ModelAdmin):
#     list_display = ('id', 'user', 'total_price', 'status', 'created_at')
#     list_filter = ('status', 'created_at')
#
# @admin.register(OrderItem)
# class OrderItemAdmin(admin.ModelAdmin):
#     list_display = ('id', 'order', 'ticket_type', 'quantity', 'price_at_purchase')
#
# @admin.register(ResaleListing)
# class ResaleListingAdmin(admin.ModelAdmin):
#     list_display = ('id', 'seller', 'order_item', 'price', 'status', 'created_at')
#     list_filter = ('status',)