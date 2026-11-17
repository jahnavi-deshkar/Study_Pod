from django.urls import path
from . import views


urlpatterns = [
    path("login/", views.login_view, name="login"),
    # Compatibility route for Django's historical login_required default.
    path("accounts/login/", views.login_view, name="accounts_login_legacy"),
    path("logout/", views.logout_view, name="logout"),

    path("dashboard/", views.dashboard, name="dashboard"),

    path("profile/", views.profile, name="profile"),

    path("notices/", views.notices, name="notices"),
    path("notices/create/", views.create_notice, name="create_notice"),

    path(
        "attendance/",
        views.attendance,
        name="attendance"
    ),

    path(
        "student-attendance/",
        views.student_attendance,
        name="student_attendance"
    ),

    path(
    "parent-attendance/",
    views.parent_attendance,
    name="parent_attendance"
    ),

    path(
    "resources/upload/",
    views.resource_upload,
    name="resource_upload"
    ),

    path(
        "resources/",
        views.resource_list,
        name="resource_list"
    ),
    path(
        "resources/student/<int:resource_id>/",
        views.student_resource_detail,
        name="student_resource_detail",
    ),
    path(
        "resources/<int:resource_id>/",
        views.teacher_resource_detail,
        name="teacher_resource_detail",
    ),
    path(
        "resources/<int:resource_id>/reindex/",
        views.teacher_resource_reindex,
        name="teacher_resource_reindex",
    ),
    path(
        "resources/<int:resource_id>/delete/",
        views.teacher_resource_delete,
        name="teacher_resource_delete",
    ),

    path(
        "assessments/create/",
        views.create_assessment,
        name="create_assessment"
    ),
    path(
        "assessments/create/assignment/",
        views.create_assessment,
        {"workflow_type": "ASSIGNMENT"},
        name="create_assignment",
    ),
    path(
        "assessments/create/test/",
        views.create_assessment,
        {"workflow_type": "TEST"},
        name="create_test",
    ),

]
