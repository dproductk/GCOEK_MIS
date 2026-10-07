from django.urls import path
from rest_framework.routers import DefaultRouter
from apps.finance.views import (
    EasebuzzCallbackView,
    EasebuzzWebhookView,
    FeeHeadViewSet,
    OnlinePaymentAttemptDetailView,
    OnlinePaymentAttemptVerifyView,
    OnlinePaymentInitiateView,
    OnlinePaymentStatusView,
    OnlinePaymentTrackerView,
    PaymentLedgerViewSet,
    StudentFeeAssessmentViewSet,
)

router = DefaultRouter()
router.register('fee-heads', FeeHeadViewSet, basename='fee-heads')
router.register('ledger', PaymentLedgerViewSet, basename='payment-ledger')
router.register('assessments', StudentFeeAssessmentViewSet, basename='fee-assessment')

urlpatterns = [
    path('online-payment/status/', OnlinePaymentStatusView.as_view(), name='online-payment-status'),
    path('online-payment/initiate/', OnlinePaymentInitiateView.as_view(), name='online-payment-initiate'),
    path('online-payment/attempt/<uuid:pk>/', OnlinePaymentAttemptDetailView.as_view(), name='online-payment-attempt-detail'),
    path('online-payment/attempt/<uuid:pk>/verify/', OnlinePaymentAttemptVerifyView.as_view(), name='online-payment-attempt-verify'),
    path('online-payment/callback/', EasebuzzCallbackView.as_view(), name='online-payment-callback'),
    path('online-payment/webhook/', EasebuzzWebhookView.as_view(), name='online-payment-webhook'),
    path('online-payment/tracker/', OnlinePaymentTrackerView.as_view(), name='online-payment-tracker'),
] + router.urls

