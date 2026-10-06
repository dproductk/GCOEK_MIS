from rest_framework.routers import DefaultRouter
from apps.faculty.views import FacultyViewSet, TeachingAssignmentViewSet

router = DefaultRouter()
router.register('assignments', TeachingAssignmentViewSet, basename='teaching-assignment')
router.register('', FacultyViewSet, basename='faculty')

urlpatterns = router.urls
