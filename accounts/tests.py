from django.test import TestCase
from django.urls import reverse

from academics.models import Attendance, Class, Subject, TeachingAssignment
from .models import TeacherProfile, User


class AttendanceAuthorizationTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=user, employee_id="T-ATTENDANCE"
        )
        self.assigned_class = Class.objects.create(
            name="10", section="A", academic_year="2026-27"
        )
        self.unassigned_class = Class.objects.create(
            name="11", section="B", academic_year="2026-27"
        )
        subject = Subject.objects.create(name="Science", code="SCI-ATTENDANCE")
        TeachingAssignment.objects.create(
            teacher=self.teacher,
            student_class=self.assigned_class,
            subject=subject,
        )
        self.client.force_login(user)

    def test_teacher_cannot_submit_attendance_for_unassigned_class(self):
        response = self.client.post(reverse("attendance"), {
            "action": "save",
            "student_class": self.unassigned_class.id,
            "date": "2026-10-04",
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Attendance.objects.exists())

    def test_teacher_can_load_an_assigned_class(self):
        response = self.client.post(reverse("attendance"), {
            "action": "load",
            "student_class": self.assigned_class.id,
            "date": "2026-10-04",
        })

        self.assertEqual(response.status_code, 200)
