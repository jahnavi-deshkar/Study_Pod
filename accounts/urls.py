from django.urls import path
from . import views


urlpatterns = [
    path("login/", views.login_view, name="login"),
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

]