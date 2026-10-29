"""
URL configuration for study_pod project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from academics import views as academic_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("academics/", include("academics.urls")),
    path("exam/", include("exam_engine.urls")),
    path("api/student/leave/apply/", academic_views.leave_apply_api, name="leave_apply_api"),
    path("api/student/leave/history/", academic_views.leave_history_api, name="leave_history_api"),
    path("api/student/leave/<int:pk>/", academic_views.leave_detail_api, name="leave_detail_api"),
    path("api/student/leave/<int:pk>/cancel/", academic_views.leave_cancel_api, name="leave_cancel_api"),
    path("api/teacher/leave/<int:pk>/review/", academic_views.leave_review_api, name="leave_review_api"),
    path("api/leave/attachments/<int:pk>/", academic_views.leave_attachment_download, name="leave_attachment_download"),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

