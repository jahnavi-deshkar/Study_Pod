from django.urls import path

from . import views


urlpatterns = [
    path("teacher/attendance/", views.teacher_attendance, name="teacher_attendance"),
    path("student/attendance/", views.student_attendance, name="academics_student_attendance"),
    path("discussions/", views.doubt_threads, name="doubt_threads"),
    path("discussions/<int:pk>/", views.doubt_thread_detail, name="doubt_thread_detail"),
    path("student/analytics/", views.student_analytics, name="student_analytics"),
    path("teacher/analytics/", views.teacher_analytics, name="teacher_analytics"),
    path("teacher/timetable/", views.teacher_timetable, name="teacher_timetable"),
    path("student/timetable/", views.student_timetable, name="student_timetable"),
    path("parent/timetable/", views.parent_timetable, name="parent_timetable"),
    path("parent/analytics/", views.student_analytics, name="parent_analytics"),
]
