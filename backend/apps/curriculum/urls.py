from rest_framework.routers import DefaultRouter

from apps.curriculum.views import (
    AssessmentComponentViewSet,
    ElectiveGroupViewSet,
    ElectiveOptionViewSet,
    SchemeSubjectViewSet,
    SchemeViewSet,
    SubjectViewSet,
)

router = DefaultRouter()
router.register('subjects', SubjectViewSet, basename='subject')
router.register('schemes', SchemeViewSet, basename='scheme')
router.register('scheme-subjects', SchemeSubjectViewSet, basename='scheme-subject')
router.register('assessment-components', AssessmentComponentViewSet, basename='assessment-component')
router.register('elective-groups', ElectiveGroupViewSet, basename='elective-group')
router.register('elective-options', ElectiveOptionViewSet, basename='elective-option')

urlpatterns = router.urls
