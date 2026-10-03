from django.urls import path

from . import views


urlpatterns = [
    path("teacher/attendance/", views.teacher_attendance, name="teacher_attendance"),
    path("student/attendance/", views.student_attendance, name="academics_student_attendance"),
    path("discussions/", views.doubt_threads, name="doubt_threads"),
    path("discussions/<int:pk>/", views.doubt_thread_detail, name="doubt_thread_detail"),
]
