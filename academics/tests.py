from io import StringIO
from datetime import date

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile, TeacherProfile, User
from exam_engine.models import AssessmentAttempt, Question, StudentAnswer

from .models import Assessment, Attendance, Class, DoubtReply, DoubtThread, Subject, TeachingAssignment, Timetable


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


class AnalyticsDashboardTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="analytics-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-ANALYTICS-1"
        )
        self.other_teacher_user = User.objects.create_user(
            username="analytics-other-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.other_teacher = TeacherProfile.objects.create(
            user=self.other_teacher_user, employee_id="T-ANALYTICS-2"
        )
        self.student_user = User.objects.create_user(
            username="analytics-student", password="test-pass", role=User.Role.STUDENT
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, roll_number="A-1"
        )
        self.class_one = Class.objects.create(name="10", section="A", academic_year="2026-27")
        self.class_two = Class.objects.create(name="10", section="B", academic_year="2026-27")
        self.student.student_class = self.class_one
        self.student.save(update_fields=["student_class"])
        self.subject_math = Subject.objects.create(name="Mathematics", code="AN-MATH")
        self.subject_science = Subject.objects.create(name="Science", code="AN-SCI")
        TeachingAssignment.objects.create(
            teacher=self.teacher, student_class=self.class_one, subject=self.subject_math
        )
        TeachingAssignment.objects.create(
            teacher=self.teacher, student_class=self.class_one, subject=self.subject_science
        )
        TeachingAssignment.objects.create(
            teacher=self.other_teacher, student_class=self.class_two, subject=self.subject_math
        )

    def make_assessment(self, title, subject, total_marks, teacher=None, student_class=None):
        return Assessment.objects.create(
            title=title,
            teacher=teacher or self.teacher,
            student_class=student_class or self.class_one,
            subject=subject,
            assessment_type=Assessment.AssessmentType.TEST,
            total_marks=total_marks,
            is_published=True,
        )

    def add_result(self, assessment, student, marks_awarded, question=None):
        question = question or Question.objects.create(
            assessment=assessment,
            question_text="Solve the problem",
            question_type=Question.QuestionType.NUMERICAL,
            marks=assessment.total_marks,
            order=1,
        )
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=student,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        StudentAnswer.objects.create(
            attempt=attempt, question=question, awarded_marks=marks_awarded
        )
        return attempt

    def test_student_analytics_uses_weighted_subject_and_overall_scores(self):
        math_test = self.make_assessment("Algebra Test", self.subject_math, 10)
        science_test = self.make_assessment("Science Test", self.subject_science, 20)
        self.make_assessment("Not Taken", self.subject_math, 5)
        self.add_result(math_test, self.student, 8)
        self.add_result(science_test, self.student, 6)

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["taken_count"], 2)
        self.assertEqual(response.context["assigned_count"], 3)
        self.assertAlmostEqual(float(response.context["average_percentage"]), 46.666, places=2)
        self.assertEqual(response.context["highest_subject"]["subject"], self.subject_math)
        self.assertEqual(response.context["lowest_subject"]["subject"], self.subject_science)
        self.assertContains(response, "Algebra Test")
        self.assertContains(response, "Science Test")

    def test_anonymous_analytics_redirects_to_the_configured_login_page(self):
        response = self.client.get(reverse("student_analytics"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('student_analytics')}",
        )
        legacy_login = self.client.get("/accounts/login/?next=/academics/student/analytics/")
        self.assertEqual(legacy_login.status_code, 200)
        self.assertContains(legacy_login, "Login")

    def test_student_analytics_is_private_and_for_student_role_only(self):
        other_student_user = User.objects.create_user(
            username="analytics-student-two", password="test-pass", role=User.Role.STUDENT
        )
        other_student = StudentProfile.objects.create(
            user=other_student_user, roll_number="A-2", student_class=self.class_one
        )
        assessment = self.make_assessment("Private Result", self.subject_math, 10)
        self.add_result(assessment, other_student, 9)
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private Result")

        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("student_analytics"))
        self.assertEqual(response.status_code, 403)

    def test_teacher_analytics_calculates_class_item_and_attention_metrics(self):
        second_student_user = User.objects.create_user(
            username="analytics-student-three", password="test-pass", role=User.Role.STUDENT
        )
        second_student = StudentProfile.objects.create(
            user=second_student_user, roll_number="A-3", student_class=self.class_one
        )
        assessment = self.make_assessment("Class Quiz", self.subject_math, 10)
        question = Question.objects.create(
            assessment=assessment,
            question_text="Find x",
            question_type=Question.QuestionType.NUMERICAL,
            marks=10,
            order=1,
        )
        self.add_result(assessment, self.student, 10, question=question)
        self.add_result(assessment, second_student, 4, question=question)
        self.client.force_login(self.teacher_user)

        response = self.client.get(reverse("teacher_analytics"), {
            "student_class": self.class_one.pk,
            "assessment": assessment.pk,
            "threshold": "50",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submissions"], 2)
        self.assertEqual(response.context["enrolled_count"], 2)
        self.assertAlmostEqual(float(response.context["average_percentage"]), 70.0, places=1)
        self.assertEqual(float(response.context["highest_score"]), 10.0)
        self.assertEqual(float(response.context["lowest_score"]), 4.0)
        self.assertEqual(len(response.context["needs_attention"]), 1)
        self.assertEqual(float(response.context["item_analysis"][0]["correct_percentage"]), 50.0)

    def test_teacher_analytics_rejects_unassigned_class_and_assessment(self):
        own_assessment = self.make_assessment("Assigned", self.subject_math, 10)
        foreign_assessment = self.make_assessment(
            "Foreign", self.subject_math, 10,
            teacher=self.other_teacher, student_class=self.class_two,
        )
        self.client.force_login(self.teacher_user)
        class_response = self.client.get(reverse("teacher_analytics"), {
            "student_class": self.class_two.pk,
        })
        assessment_response = self.client.get(reverse("teacher_analytics"), {
            "student_class": self.class_one.pk,
            "assessment": foreign_assessment.pk,
        })
        self.assertEqual(class_response.status_code, 403)
        self.assertEqual(assessment_response.status_code, 403)


class SeedDataCommandTests(TestCase):
    def test_seed_command_is_repeatable(self):
        call_command("seed_data", stdout=StringIO())
        call_command("seed_data", stdout=StringIO())

        self.assertEqual(User.objects.filter(username__in=["teacher1", "student1", "student2"]).count(), 3)
        self.assertEqual(Class.objects.filter(name="10", section="A", academic_year="2026-27").count(), 1)
        self.assertEqual(Subject.objects.filter(code__in=["SEED-MATH", "SEED-SCI"]).count(), 2)
        self.assertEqual(Assessment.objects.filter(title="Sample Mathematics Assessment").count(), 1)
        self.assertEqual(Timetable.objects.count(), 2)


class TimetableAccessTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="schedule-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-SCHEDULE"
        )
        self.student_class = Class.objects.create(
            name="7", section="A", academic_year="2026-27"
        )
        self.other_class = Class.objects.create(
            name="7", section="B", academic_year="2026-27"
        )
        self.subject = Subject.objects.create(name="History", code="HISTORY-SCHEDULE")
        TeachingAssignment.objects.create(
            teacher=self.teacher, student_class=self.student_class, subject=self.subject
        )
        self.own_entry = Timetable.objects.create(
            student_class=self.student_class,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=Timetable.DayOfWeek.MONDAY,
            start_time="09:00",
            end_time="09:45",
            room_number="204",
        )
        self.other_entry = Timetable.objects.create(
            student_class=self.other_class,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=Timetable.DayOfWeek.TUESDAY,
            start_time="10:00",
            end_time="10:45",
        )
        self.student_user = User.objects.create_user(
            username="schedule-student", password="test-pass", role=User.Role.STUDENT
        )
        StudentProfile.objects.create(
            user=self.student_user, roll_number="S-SCHEDULE", student_class=self.student_class
        )

    def test_student_only_sees_timetable_for_own_class(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_timetable"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "History")
        self.assertContains(response, "Room 204")
        self.assertNotContains(response, str(self.other_class))

    def test_teacher_sees_only_assigned_class_subject_slots(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("teacher_timetable"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "History")
        self.assertContains(response, str(self.student_class))
        self.assertNotContains(response, str(self.other_class))

    def test_roles_cannot_open_the_other_role_timetable(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("teacher_timetable"))
        self.assertRedirects(response, reverse("dashboard"))
