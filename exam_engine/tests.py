from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile, TeacherProfile, User
from academics.models import Assessment, Class, Subject, TeachingAssignment
from .models import AssessmentAttempt, Question, QuestionOption, StudentAnswer


class AssessmentFlowTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-TEST"
        )
        self.student_user = User.objects.create_user(
            username="student", password="test-pass", role=User.Role.STUDENT
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, roll_number="S-TEST"
        )
        self.student_class = Class.objects.create(
            name="10", section="A", academic_year="2026-27"
        )
        self.student.student_class = self.student_class
        self.student.save(update_fields=["student_class"])
        self.subject = Subject.objects.create(name="Mathematics", code="MATH-TEST")
        TeachingAssignment.objects.create(
            teacher=self.teacher,
            student_class=self.student_class,
            subject=self.subject,
        )

    def make_assessment(self, **overrides):
        values = {
            "title": "Unit Test",
            "teacher": self.teacher,
            "student_class": self.student_class,
            "subject": self.subject,
            "assessment_type": Assessment.AssessmentType.TEST,
            "total_marks": 10,
            "is_published": True,
        }
        values.update(overrides)
        return Assessment.objects.create(**values)

    def add_question(self, assessment, **overrides):
        values = {
            "assessment": assessment,
            "question_text": "What is 2 + 2?",
            "question_type": Question.QuestionType.MCQ_SINGLE,
            "marks": 2,
            "order": 1,
        }
        values.update(overrides)
        question = Question.objects.create(**values)
        QuestionOption.objects.create(
            question=question, option_text="4", is_correct=True, order=1
        )
        QuestionOption.objects.create(
            question=question, option_text="5", is_correct=False, order=2
        )
        return question

    def test_untimed_assessment_creates_attempt_without_expiry(self):
        assessment = self.make_assessment(timing_mode=Assessment.TimingMode.NONE)
        self.add_question(assessment)
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("student_test", args=[assessment.id]))

        self.assertEqual(response.status_code, 200)
        attempt = AssessmentAttempt.objects.get(assessment=assessment, student=self.student)
        self.assertIsNone(attempt.expires_at)
        self.assertNotContains(response, "id=\"countdown\"")

    def test_entire_test_mode_sets_attempt_expiry(self):
        assessment = self.make_assessment(
            timing_mode=Assessment.TimingMode.ENTIRE_TEST,
            duration_hours=1,
            duration_minutes=15,
        )
        self.add_question(assessment)
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("student_test", args=[assessment.id]))

        self.assertEqual(response.status_code, 200)
        attempt = AssessmentAttempt.objects.get(assessment=assessment, student=self.student)
        self.assertIsNotNone(attempt.expires_at)
        self.assertAlmostEqual(
            (attempt.expires_at - attempt.started_at).total_seconds(),
            4500,
            delta=2,
        )
        self.assertContains(response, "id=\"countdown\"")

    def test_per_question_mode_sets_question_deadline(self):
        assessment = self.make_assessment(timing_mode=Assessment.TimingMode.PER_QUESTION)
        question = self.add_question(
            assessment, time_limit_minutes=2
        )
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("student_test", args=[assessment.id]))

        self.assertEqual(response.status_code, 200)
        attempt = AssessmentAttempt.objects.get(assessment=assessment, student=self.student)
        answer = StudentAnswer.objects.get(attempt=attempt, question=question)
        self.assertIsNone(attempt.expires_at)
        self.assertIsNotNone(answer.question_expires_at)
        self.assertContains(response, "id=\"countdown\"")

    def test_ajax_answer_save_is_preserved(self):
        assessment = self.make_assessment(timing_mode=Assessment.TimingMode.NONE)
        question = self.add_question(assessment)
        option = question.options.get(is_correct=True)
        self.client.force_login(self.student_user)
        self.client.get(reverse("student_test", args=[assessment.id]))

        response = self.client.post(
            f"{reverse('student_test', args=[assessment.id])}?question=1",
            {
                "question_number": "1",
                "action": "stay",
                "answer": str(option.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"saved": True})
        answer = StudentAnswer.objects.get(
            attempt__assessment=assessment,
            attempt__student=self.student,
            question=question,
        )
        self.assertEqual(answer.selected_option_id, option.id)

    def test_unpublished_and_out_of_window_assessments_cannot_start(self):
        self.client.force_login(self.student_user)
        unpublished = self.make_assessment(is_published=False)
        self.add_question(unpublished)
        response = self.client.get(reverse("student_test", args=[unpublished.id]))
        self.assertRedirects(response, reverse("student_assessments"))
        self.assertFalse(AssessmentAttempt.objects.filter(assessment=unpublished).exists())

        future = self.make_assessment(
            title="Future Test", available_from=timezone.now() + timedelta(hours=1)
        )
        self.add_question(future)
        response = self.client.get(reverse("student_test", args=[future.id]))
        self.assertRedirects(response, reverse("student_assessments"))
        self.assertFalse(AssessmentAttempt.objects.filter(assessment=future).exists())

        expired = self.make_assessment(
            title="Past Test", due_date=timezone.now() - timedelta(hours=1)
        )
        self.add_question(expired)
        response = self.client.get(reverse("student_test", args=[expired.id]))
        self.assertRedirects(response, reverse("student_assessments"))
        self.assertFalse(AssessmentAttempt.objects.filter(assessment=expired).exists())

    def test_student_list_only_shows_published_assessments(self):
        published = self.make_assessment()
        self.make_assessment(title="Draft", is_published=False)
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("student_assessments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, published.title)
        self.assertNotContains(response, "Draft")

    def test_teacher_can_publish_assessment_from_preview(self):
        assessment = self.make_assessment(is_published=False)
        self.add_question(assessment)
        self.client.force_login(self.teacher_user)

        response = self.client.post(
            reverse("test_preview", args=[assessment.id]),
            {"action": "publish"},
        )

        self.assertRedirects(response, reverse("test_preview", args=[assessment.id]))
        assessment.refresh_from_db()
        self.assertTrue(assessment.is_published)

    def test_teacher_attempt_templates_render_and_routes_resolve(self):
        assessment = self.make_assessment()
        question = self.add_question(assessment)
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=self.student,
            started_at=timezone.now(),
            expires_at=None,
            status=AssessmentAttempt.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        StudentAnswer.objects.create(
            attempt=attempt,
            question=question,
            answer_text="",
            awarded_marks=2,
        )
        self.client.force_login(self.teacher_user)

        list_response = self.client.get(reverse("teacher_attempts", args=[assessment.id]))
        detail_response = self.client.get(
            reverse("teacher_attempt_detail", args=[assessment.id, attempt.id])
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(list_response, "Student Attempts")
        self.assertContains(detail_response, "Attempt Details")

    def test_question_creation_rejects_mcq_without_options_or_correct_answer(self):
        assessment = self.make_assessment()
        self.client.force_login(self.teacher_user)
        url = reverse("question_create", args=[assessment.id])

        response = self.client.post(url, {
            "question_text": "Choose the right answer",
            "question_type": "MCQ_SINGLE",
            "marks": "1",
            "option_text": ["Option A", "Option B"],
            "action": "next",
        })

        self.assertRedirects(response, url)
        self.assertFalse(assessment.questions.exists())

        response = self.client.post(url, {
            "question_text": "Choose the right answer",
            "question_type": "MCQ_SINGLE",
            "marks": "1",
            "option_text": ["Option A", "Option B"],
            "correct_option": ["0"],
            "action": "next",
        })

        self.assertEqual(response.status_code, 302)
        question = assessment.questions.get()
        self.assertEqual(question.options.count(), 2)
        self.assertEqual(question.options.filter(is_correct=True).count(), 1)
