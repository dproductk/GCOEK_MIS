"""
Academic Structure URL configuration.
"""
from rest_framework.routers import DefaultRouter

from apps.academic_structure.views import (
    AcademicContextViewSet,
    AcademicYearViewSet,
    DepartmentViewSet,
    DivisionViewSet,
    LabBatchViewSet,
    ProgramViewSet,
    SemesterViewSet,
)

router = DefaultRouter()
router.register('departments', DepartmentViewSet, basename='academic-department')
router.register('programs', ProgramViewSet, basename='academic-program')
router.register('years', AcademicYearViewSet, basename='academic-year')
router.register('academic-years', AcademicYearViewSet, basename='academic-year-alias')
router.register('contexts', AcademicContextViewSet, basename='academic-context')
router.register('academic-contexts', AcademicContextViewSet, basename='academic-context-alias')
router.register('semesters', SemesterViewSet, basename='academic-semester')
router.register('divisions', DivisionViewSet, basename='academic-division')
router.register('lab-batches', LabBatchViewSet, basename='academic-lab-batch')

urlpatterns = router.urls
