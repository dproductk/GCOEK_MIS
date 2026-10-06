from rest_framework.routers import DefaultRouter
from apps.audit.views import AuditLogViewSet

router = DefaultRouter()
router.register('logs', AuditLogViewSet, basename='audit-logs')

urlpatterns = router.urls
