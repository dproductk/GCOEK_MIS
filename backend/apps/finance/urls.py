from rest_framework.routers import DefaultRouter
from apps.finance.views import FeeHeadViewSet, PaymentLedgerViewSet, StudentFeeAssessmentViewSet

router = DefaultRouter()
router.register('fee-heads', FeeHeadViewSet, basename='fee-heads')
router.register('ledger', PaymentLedgerViewSet, basename='payment-ledger')
router.register('assessments', StudentFeeAssessmentViewSet, basename='fee-assessment')

urlpatterns = router.urls
