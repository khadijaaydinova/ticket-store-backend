from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EventViewSet, OrderViewSet, TicketViewSet, ScanTicketView, SpeakerViewSet, AgendaSessionViewSet, \
    MyScheduleViewSet, AbstractSubmissionViewSet, SponsorViewSet, LivePollViewSet, QAQuestionViewSet
# events/urls.py
from rest_framework.routers import DefaultRouter
from .views import ResaleViewSet # импортируем наш новый вьюсет
from rest_framework.routers import DefaultRouter
from .views import MembershipViewSet


# ... остальной код urls.py
router = DefaultRouter()
router.register(r'events', EventViewSet)
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'tickets', TicketViewSet, basename='ticket')
router.register(r'resale', ResaleViewSet, basename='resale')
router.register(r'memberships', MembershipViewSet, basename='membership')
router.register(r'speakers', SpeakerViewSet)
router.register(r'sessions', AgendaSessionViewSet)
router.register(r'my-schedule', MyScheduleViewSet, basename='my-schedule')
router.register(r'sponsors', SponsorViewSet)
router.register(r'submissions', AbstractSubmissionViewSet, basename='submissions')
router.register(r'qa-questions', QAQuestionViewSet, basename='qa-questions')
router.register(r'live-polls', LivePollViewSet, basename='live-polls')


urlpatterns = [
    path('scan/', ScanTicketView.as_view(), name='scan-ticket'),
    path('', include(router.urls)),
    path('api/', include(router.urls)), # Добавляем префикс /api/resale/
] + router.urls
