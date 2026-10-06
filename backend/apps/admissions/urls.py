from rest_framework.routers import DefaultRouter
from apps.admissions.views import AdmissionImportViewSet

router = DefaultRouter()
router.register('batches', AdmissionImportViewSet, basename='admission-batches')

urlpatterns = router.urls
