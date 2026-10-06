"""
GCOEK MIS — Root URL Configuration

All API endpoints are versioned under /api/v1/.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.authentication.urls')),
    path('api/v1/academic/', include('apps.academic_structure.urls')),
    path('api/v1/students/', include('apps.students.urls')),
    path('api/v1/faculty/', include('apps.faculty.urls')),
    path('api/v1/admissions/', include('apps.admissions.urls')),
    path('api/v1/results/', include('apps.results.urls')),
    path('api/v1/finance/', include('apps.finance.urls')),
    path('api/v1/audit/', include('apps.audit.urls')),
    path('api/v1/curriculum/', include('apps.curriculum.urls')),
]


