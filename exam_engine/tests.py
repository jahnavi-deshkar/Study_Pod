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

    def test_short_answer_submission_waits_for_teacher_and_result_updates(self):
        assessment = self.make_assessment(total_marks=5)
        objective_question = self.add_question(assessment)
        short_question = Question.objects.create(
            assessment=assessment,
            question_text="Explain your reasoning.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            marks=3,
            order=2,
        )
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=self.student,
            started_at=timezone.now(),
            expires_at=None,
        )
        StudentAnswer.objects.create(
            attempt=attempt,
            question=objective_question,
            selected_option=objective_question.options.get(is_correct=True),
        )
        short_answer = StudentAnswer.objects.create(
            attempt=attempt,
            question=short_question,
            answer_text="Because the two quantities are equal.",
        )

        self.client.force_login(self.student_user)
        response = self.client.post(reverse("student_submit", args=[assessment.id]))

        self.assertRedirects(response, reverse("student_result", args=[assessment.id]))
        attempt.refresh_from_db()
        short_answer.refresh_from_db()
        self.assertEqual(attempt.status, AssessmentAttempt.Status.NEEDS_EVALUATION)
        self.assertEqual(short_answer.awarded_marks, None)
        self.assertEqual(attempt.score, 2)

        self.client.force_login(self.teacher_user)
        detail_url = reverse("teacher_attempt_detail", args=[assessment.id, attempt.id])
        response = self.client.post(detail_url, {
            f"marks_awarded_{short_answer.id}": "4",
            f"teacher_feedback_{short_answer.id}": "Good explanation.",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "must be between 0 and 3")
        short_answer.refresh_from_db()
        self.assertIsNone(short_answer.awarded_marks)

        response = self.client.post(detail_url, {
            f"marks_awarded_{short_answer.id}": "2.5",
            f"teacher_feedback_{short_answer.id}": "Good explanation.",
        })
        self.assertRedirects(response, detail_url)
        attempt.refresh_from_db()
        short_answer.refresh_from_db()
        self.assertEqual(attempt.status, AssessmentAttempt.Status.EVALUATED)
        self.assertEqual(attempt.score, 4.5)
        self.assertEqual(attempt.percentage, 90)
        self.assertEqual(short_answer.teacher_feedback, "Good explanation.")

        self.client.force_login(self.student_user)
        result = self.client.get(reverse("student_result", args=[assessment.id]))
        self.assertContains(result, "Evaluated")
        self.assertContains(result, "Good explanation.")
        self.assertContains(result, "90.0%")

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

    def test_attempt_limit_blocks_additional_starts_but_allows_unlimited(self):
        limited = self.make_assessment(max_attempts=1)
        self.add_question(limited)
        AssessmentAttempt.objects.create(
            assessment=limited,
            student=self.student,
            started_at=timezone.now() - timedelta(minutes=5),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("student_test", args=[limited.pk]))
        self.assertRedirects(response, reverse("student_result", args=[limited.pk]))
        self.assertEqual(AssessmentAttempt.objects.filter(assessment=limited).count(), 1)

        unlimited = self.make_assessment(title="Unlimited Test", max_attempts=0)
        self.add_question(unlimited)
        AssessmentAttempt.objects.create(
            assessment=unlimited,
            student=self.student,
            started_at=timezone.now() - timedelta(minutes=5),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        response = self.client.get(reverse("student_test", args=[unlimited.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssessmentAttempt.objects.filter(assessment=unlimited).count(), 2)

    def test_access_code_is_required_before_attempt_initialization(self):
        assessment = self.make_assessment(access_code="SCIENCE42")
        self.add_question(assessment)
        self.client.force_login(self.student_user)

        instructions = self.client.get(reverse("student_assessment_instructions", args=[assessment.pk]))
        self.assertEqual(instructions.status_code, 200)
        self.assertContains(instructions, "access_code")
        self.assertFalse(AssessmentAttempt.objects.filter(assessment=assessment).exists())

        wrong = self.client.post(reverse("student_test", args=[assessment.pk]), {
            "access_code": "WRONG",
        })
        self.assertRedirects(wrong, reverse("student_assessment_instructions", args=[assessment.pk]))
        self.assertFalse(AssessmentAttempt.objects.filter(assessment=assessment).exists())

        correct = self.client.post(reverse("student_test", args=[assessment.pk]), {
            "access_code": "SCIENCE42",
        })
        self.assertRedirects(correct, reverse("student_test", args=[assessment.pk]))
        self.assertTrue(AssessmentAttempt.objects.filter(assessment=assessment, student=self.student).exists())

    def test_shuffled_question_order_is_stable_for_each_attempt_and_keeps_options(self):
        assessment = self.make_assessment(shuffle_questions=True)
        questions = [self.add_question(assessment, question_text=f"Question {number}", order=number)
                     for number in range(1, 9)]
        self.client.force_login(self.student_user)

        first = self.client.get(reverse("student_test", args=[assessment.pk]))
        first_order = [item["question_id"] for item in first.context["question_navigation"]]
        second = self.client.get(reverse("student_test", args=[assessment.pk]) + "?question=2")
        second_order = [item["question_id"] for item in second.context["question_navigation"]]

        self.assertEqual(set(first_order), {question.pk for question in questions})
        self.assertEqual(first_order, second_order)
        self.assertEqual(first.context["question"].options.count(), 2)

    def test_results_can_be_withheld_and_released_by_assessment_teacher(self):
        assessment = self.make_assessment(show_results_immediately=False)
        question = self.add_question(assessment)
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=self.student,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        StudentAnswer.objects.create(attempt=attempt, question=question, awarded_marks=2)
        self.client.force_login(self.student_user)

        hidden_result = self.client.get(reverse("student_result", args=[assessment.pk]))
        self.assertContains(hidden_result, "Results pending")
        self.assertNotContains(hidden_result, "Your Score")

        self.client.force_login(self.teacher_user)
        released = self.client.post(reverse("test_preview", args=[assessment.pk]), {
            "action": "release_results",
        })
        self.assertRedirects(released, reverse("test_preview", args=[assessment.pk]))
        assessment.refresh_from_db()
        self.assertTrue(assessment.results_released)

        self.client.force_login(self.student_user)
        visible_result = self.client.get(reverse("student_result", args=[assessment.pk]))
        self.assertContains(visible_result, "Your Score")

    def test_teacher_can_update_advanced_assessment_configuration(self):
        assessment = self.make_assessment()
        self.client.force_login(self.teacher_user)

        response = self.client.post(reverse("test_management"), {
            "action": "update_configuration",
            "assessment_id": assessment.pk,
            "max_attempts": "3",
            "shuffle_questions": "on",
            "show_results_immediately": "on",
            "passmark_percentage": "55.5",
            "access_code": "CLASS-10",
            "instructions": "Read every question carefully.",
        })

        self.assertRedirects(response, reverse("test_management"))
        assessment.refresh_from_db()
        self.assertEqual(assessment.max_attempts, 3)
        self.assertTrue(assessment.shuffle_questions)
        self.assertEqual(assessment.passmark_percentage, 55.5)
        self.assertEqual(assessment.access_code, "CLASS-10")
        self.assertEqual(assessment.instructions, "Read every question carefully.")

    def test_submitted_attempt_rejects_ajax_answer_changes(self):
        assessment = self.make_assessment(max_attempts=0)
        question = self.add_question(assessment)
        original_option = question.options.get(is_correct=True)
        changed_option = question.options.get(is_correct=False)
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=self.student,
            started_at=timezone.now() - timedelta(minutes=1),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        answer = StudentAnswer.objects.create(
            attempt=attempt,
            question=question,
            selected_option=original_option,
            awarded_marks=question.marks,
        )
        self.client.force_login(self.student_user)

        response = self.client.post(
            reverse("student_test", args=[assessment.pk]),
            {"question_number": "1", "action": "stay", "answer": str(changed_option.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)
        answer.refresh_from_db()
        self.assertEqual(answer.selected_option_id, original_option.pk)
        self.assertEqual(answer.awarded_marks, question.marks)

    def test_student_result_and_attempt_access_are_scoped_to_logged_in_student(self):
        assessment = self.make_assessment()
        question = self.add_question(assessment)
        other_user = User.objects.create_user(
            username="other-assessment-student", password="test-pass", role=User.Role.STUDENT
        )
        other_student = StudentProfile.objects.create(
            user=other_user, roll_number="S-OTHER", student_class=self.student_class
        )
        other_attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=other_student,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        StudentAnswer.objects.create(
            attempt=other_attempt,
            question=question,
            answer_text="private answer",
            awarded_marks=question.marks,
        )
        self.client.force_login(self.student_user)

        result = self.client.get(reverse("student_result", args=[assessment.pk]))
        self.assertRedirects(result, reverse("student_assessments"))
        self.assertFalse(AssessmentAttempt.objects.filter(
            assessment=assessment, student=self.student
        ).exists())

        started = self.client.get(
            reverse("student_test", args=[assessment.pk]) + f"?attempt_id={other_attempt.pk}"
        )
        self.assertEqual(started.status_code, 200)
        own_attempt = AssessmentAttempt.objects.get(assessment=assessment, student=self.student)
        self.assertNotEqual(own_attempt.pk, other_attempt.pk)
        self.assertNotContains(started, "private answer")

    def test_teacher_attempt_views_reject_non_owner(self):
        assessment = self.make_assessment()
        question = self.add_question(assessment)
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=self.student,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        other_teacher_user = User.objects.create_user(
            username="assessment-outsider-teacher", password="test-pass", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=other_teacher_user, employee_id="T-OUTSIDER")
        self.client.force_login(other_teacher_user)

        attempts_response = self.client.get(reverse("teacher_attempts", args=[assessment.pk]))
        detail_response = self.client.get(reverse(
            "teacher_attempt_detail", args=[assessment.pk, attempt.pk]
        ))
        preview_response = self.client.get(reverse("test_preview", args=[assessment.pk]))

        self.assertEqual(attempts_response.status_code, 302)
        self.assertEqual(detail_response.status_code, 302)
        self.assertEqual(preview_response.status_code, 302)
