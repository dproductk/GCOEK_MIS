from rest_framework.routers import DefaultRouter
from apps.results.views import EligibilityVerificationViewSet, SemesterResultViewSet

router = DefaultRouter()
router.register('semester-results', SemesterResultViewSet, basename='semester-results')
router.register('eligibility', EligibilityVerificationViewSet, basename='eligibility')

urlpatterns = router.urls
