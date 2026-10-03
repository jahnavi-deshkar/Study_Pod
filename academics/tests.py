from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile, TeacherProfile, User
from .models import Attendance, Class, DoubtReply, DoubtThread, Subject, TeachingAssignment


class AttendanceWorkflowTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="attendance-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-ACADEMIC-ATT"
        )
        self.student_class = Class.objects.create(
            name="10", section="A", academic_year="2026-27"
        )
        self.other_class = Class.objects.create(
            name="11", section="B", academic_year="2026-27"
        )
        self.subject = Subject.objects.create(name="Science", code="SCI-ATT-WORKFLOW")
        TeachingAssignment.objects.create(
            teacher=self.teacher,
            student_class=self.student_class,
            subject=self.subject,
        )
        self.student_one = self.make_student("att-student-one", "R-1")
        self.student_two = self.make_student("att-student-two", "R-2")
        self.other_student = self.make_student(
            "att-other-student", "R-3", student_class=self.other_class
        )

    def make_student(self, username, roll_number, student_class=None):
        user = User.objects.create_user(
            username=username, password="test-pass", role=User.Role.STUDENT
        )
        return StudentProfile.objects.create(
            user=user,
            roll_number=roll_number,
            student_class=student_class or self.student_class,
        )

    def test_teacher_selection_defaults_to_today_and_only_lists_assigned_classes(self):
        self.client.force_login(self.teacher_user)

        response = self.client.get(reverse("teacher_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, timezone.localdate().isoformat())
        self.assertContains(response, str(self.student_class))
        self.assertNotContains(response, str(self.other_class))

    def test_teacher_can_load_existing_records_with_status_and_notes(self):
        record = Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=date(2026, 10, 4),
            status=Attendance.Status.LATE,
            remarks="Arrived after the bell",
            marked_by=self.teacher,
        )
        self.assertFalse(record.is_present)
        self.client.force_login(self.teacher_user)

        response = self.client.post(reverse("teacher_attendance"), {
            "action": "load",
            "student_class": self.student_class.id,
            "date": "2026-10-04",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="status_%s" value="LATE" checked' % self.student_one.id)
        self.assertContains(response, "Arrived after the bell")

    def test_teacher_batch_save_creates_and_updates_roster_records(self):
        existing = Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=date(2026, 10, 4),
            status=Attendance.Status.ABSENT,
            marked_by=self.teacher,
        )
        self.client.force_login(self.teacher_user)

        response = self.client.post(reverse("teacher_attendance"), {
            "action": "save",
            "student_class": self.student_class.id,
            "date": "2026-10-04",
            f"status_{self.student_one.id}": "PRESENT",
            f"remarks_{self.student_one.id}": "",
            f"status_{self.student_two.id}": "LATE",
            f"remarks_{self.student_two.id}": "Bus delay",
        })

        self.assertRedirects(
            response,
            f"{reverse('teacher_attendance')}?student_class={self.student_class.id}&date=2026-10-04",
        )
        existing.refresh_from_db()
        self.assertEqual(existing.status, Attendance.Status.PRESENT)
        self.assertTrue(existing.is_present)
        created = Attendance.objects.get(student=self.student_two, date=date(2026, 10, 4))
        self.assertEqual(created.status, Attendance.Status.LATE)
        self.assertEqual(created.remarks, "Bus delay")
        self.assertEqual(Attendance.objects.filter(date=date(2026, 10, 4)).count(), 2)

    def test_teacher_cannot_access_or_save_unassigned_class(self):
        self.client.force_login(self.teacher_user)

        response = self.client.post(reverse("teacher_attendance"), {
            "action": "save",
            "student_class": self.other_class.id,
            "date": "2026-10-04",
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Attendance.objects.exists())

    def test_student_sees_only_own_records_and_correct_metrics(self):
        test_date = date(2026, 10, 4)
        Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=test_date,
            status=Attendance.Status.PRESENT,
            remarks="Own private note",
            marked_by=self.teacher,
        )
        Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=date(2026, 10, 3),
            status=Attendance.Status.LATE,
            marked_by=self.teacher,
        )
        Attendance.objects.create(
            student=self.student_two,
            student_class=self.student_class,
            date=test_date,
            status=Attendance.Status.ABSENT,
            remarks="Other student's note",
            marked_by=self.teacher,
        )
        self.client.force_login(self.student_one.user)

        response = self.client.get(reverse("academics_student_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Classes Held")
        self.assertContains(response, "2")
        self.assertContains(response, "50.0%")
        self.assertContains(response, "Own private note")
        self.assertNotContains(response, "Other student's note")


class DoubtForumTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="forum-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-FORUM-1"
        )
        self.student_class = Class.objects.create(
            name="9", section="A", academic_year="2026-27"
        )
        self.other_class = Class.objects.create(
            name="9", section="B", academic_year="2026-27"
        )
        self.subject = Subject.objects.create(name="Maths", code="MATH-FORUM")
        TeachingAssignment.objects.create(
            teacher=self.teacher,
            student_class=self.student_class,
            subject=self.subject,
        )
        self.student = self.make_student("forum-student", "F-1", self.student_class)
        self.classmate = self.make_student("forum-classmate", "F-2", self.student_class)
        self.outsider = self.make_student("forum-outsider", "F-3", self.other_class)

    def make_student(self, username, roll_number, student_class):
        user = User.objects.create_user(
            username=username, password="test-pass", role=User.Role.STUDENT
        )
        return StudentProfile.objects.create(
            user=user, roll_number=roll_number, student_class=student_class
        )

    def make_thread(self, student=None, student_class=None):
        return DoubtThread.objects.create(
            title="How do fractions work?",
            content="Please explain the common denominator.",
            student=student or self.student,
            student_class=student_class or self.student_class,
            subject=self.subject,
        )

    def test_student_can_create_thread_for_class_subject(self):
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("doubt_threads"), {
            "student_class": self.student_class.pk,
            "subject": self.subject.pk,
            "title": "Help with fractions",
            "content": "How do I find a common denominator?",
        })
        thread = DoubtThread.objects.get(title="Help with fractions")
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertEqual(thread.student, self.student)
        self.assertEqual(thread.student_class, self.student_class)

    def test_student_cannot_create_thread_for_another_class(self):
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("doubt_threads"), {
            "student_class": self.other_class.pk,
            "subject": self.subject.pk,
            "title": "Out of class",
            "content": "This should not be saved.",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DoubtThread.objects.exists())

    def test_classmate_and_assigned_teacher_can_reply(self):
        thread = self.make_thread()
        self.client.force_login(self.classmate.user)
        response = self.client.post(reverse("doubt_thread_detail", args=[thread.pk]), {
            "action": "reply", "content": "Try converting to eighths."
        })
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertFalse(DoubtReply.objects.get().is_teacher_reply)

        self.client.force_login(self.teacher_user)
        response = self.client.post(reverse("doubt_thread_detail", args=[thread.pk]), {
            "action": "reply", "content": "Here is a worked example."
        })
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertTrue(DoubtReply.objects.get(user=self.teacher_user).is_teacher_reply)

    def test_other_class_cannot_view_thread(self):
        thread = self.make_thread()
        self.client.force_login(self.outsider.user)
        response = self.client.get(reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertEqual(response.status_code, 403)

    def test_teacher_must_be_assigned_to_thread_subject(self):
        thread = self.make_thread()
        another_teacher_user = User.objects.create_user(
            username="forum-other-teacher", password="test-pass", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(
            user=another_teacher_user, employee_id="T-FORUM-2"
        )
        self.client.force_login(another_teacher_user)
        response = self.client.get(reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertEqual(response.status_code, 403)

    def test_author_can_toggle_resolved_status(self):
        thread = self.make_thread()
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("doubt_thread_detail", args=[thread.pk]), {
            "action": "resolve"
        })
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        thread.refresh_from_db()
        self.assertEqual(thread.status, DoubtThread.Status.RESOLVED)
