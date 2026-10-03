import hmac
import random
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from academics.models import Assessment

from .models import (
    Question,
    QuestionOption,
    QuestionImage,
    AssessmentAttempt,
    StudentAnswer,
)
from .forms import AssessmentConfigurationForm


def _availability_error(assessment, now=None):
    """Return a student-facing explanation when an assessment is unavailable."""
    now = now or timezone.now()

    if not assessment.is_published:
        return "This assessment is not available yet."
    if assessment.available_from and now < assessment.available_from:
        return "This assessment is not available yet. Please check back later."
    if assessment.due_date and now > assessment.due_date:
        return "The deadline for this assessment has passed."
    return None


def _attempt_expired(attempt, now=None):
    now = now or timezone.now()
    return attempt.expires_at is not None and now >= attempt.expires_at


# =========================================================
# TEACHER
# =========================================================


@login_required
def test_management(request):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    invalid_form = None
    invalid_assessment_id = None
    if request.method == "POST" and request.POST.get("action") == "update_configuration":
        assessment = Assessment.objects.filter(
            pk=request.POST.get("assessment_id"), teacher=teacher
        ).first()
        if assessment is None:
            messages.error(request, "Assessment not found or you do not have permission to edit it.")
            return redirect("test_management")
        form = AssessmentConfigurationForm(request.POST, instance=assessment)
        if form.is_valid():
            form.save()
            messages.success(request, "Assessment configuration updated.")
            return redirect("test_management")
        messages.error(request, "Please correct the assessment configuration fields.")
        invalid_form = form
        invalid_assessment_id = assessment.pk

    assessments = Assessment.objects.filter(
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    ).order_by("-created_at")

    for assessment in assessments:
        assessment.configuration_form = (
            invalid_form if assessment.pk == invalid_assessment_id
            else AssessmentConfigurationForm(instance=assessment)
        )

    return render(
        request,
        "exam_engine/test_management.html",
        {
            "assessments": assessments,
        }
    )


@login_required
def question_create(request, assessment_id):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    assessment = Assessment.objects.filter(
        id=assessment_id,
        teacher=teacher
    ).first()

    if not assessment:
        messages.error(
            request,
            "Assessment not found or you do not have permission to edit it."
        )
        return redirect("dashboard")

    next_question_number = assessment.questions.count() + 1

    if request.method == "POST":
        action = request.POST.get("action", "next")
        question_text = (request.POST.get("question_text") or "").strip()
        question_type = request.POST.get("question_type")
        option_texts = request.POST.getlist("option_text")
        correct_options = set(request.POST.getlist("correct_option"))
        valid_types = {value for value, _label in Question.QuestionType.choices}

        errors = []
        if not question_text:
            errors.append("Please enter the question text.")
        if question_type not in valid_types:
            errors.append("Please select a valid question type.")

        try:
            marks = int(request.POST.get("marks", ""))
            if marks < 1:
                raise ValueError
        except (TypeError, ValueError):
            marks = 1
            errors.append("Marks must be a positive whole number.")

        clean_options = [text.strip() for text in option_texts]
        nonempty_option_indexes = {
            str(index) for index, text in enumerate(clean_options) if text
        }
        correct_nonempty = correct_options & nonempty_option_indexes
        if question_type in (
            Question.QuestionType.MCQ_SINGLE,
            Question.QuestionType.MCQ_MULTI,
        ):
            if len([text for text in clean_options if text]) < 2:
                errors.append("MCQ questions must have at least two non-empty options.")
            if not correct_nonempty:
                errors.append("Select at least one correct option for this MCQ.")
            if question_type == Question.QuestionType.MCQ_SINGLE and len(correct_nonempty) != 1:
                errors.append("Select exactly one correct option for a single-correct MCQ.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("question_create", assessment_id=assessment.id)

        negative_marks = request.POST.get("negative_marks") or 0
        try:
            negative_marks = Decimal(negative_marks)
            if negative_marks < 0:
                raise ValueError
        except Exception:
            messages.error(request, "Negative marks must be zero or greater.")
            return redirect("question_create", assessment_id=assessment.id)

        time_limit_hours = request.POST.get("time_limit_hours") or 0
        time_limit_minutes = request.POST.get("time_limit_minutes") or 0
        try:
            time_limit_hours = max(0, int(time_limit_hours))
            time_limit_minutes = int(time_limit_minutes)
            if time_limit_minutes < 0 or time_limit_minutes > 59:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Question time must use non-negative hours and 0–59 minutes.")
            return redirect("question_create", assessment_id=assessment.id)

        if assessment.timing_mode != Assessment.TimingMode.PER_QUESTION:
            time_limit_hours = 0
            time_limit_minutes = 0

        correct_answer = ""
        if question_type == Question.QuestionType.TRUE_FALSE:
            correct_answer = request.POST.get("true_false_answer", "")
            if correct_answer not in ("True", "False"):
                messages.error(request, "Select the correct True / False answer.")
                return redirect("question_create", assessment_id=assessment.id)
        elif question_type == Question.QuestionType.NUMERICAL:
            correct_answer = (request.POST.get("numerical_answer") or "").strip()
            if not correct_answer:
                messages.error(request, "Enter the correct numerical answer.")
                return redirect("question_create", assessment_id=assessment.id)
        elif question_type == Question.QuestionType.SHORT_ANSWER:
            correct_answer = (request.POST.get("short_answer") or "").strip()

        question = Question.objects.create(
            assessment=assessment,
            question_text=question_text,
            question_type=question_type,
            marks=marks,
            negative_marking=request.POST.get("negative_marking") == "on",
            negative_marks=negative_marks,
            correct_answer=correct_answer,
            time_limit_hours=time_limit_hours,
            time_limit_minutes=time_limit_minutes,
            order=next_question_number,
        )

        if question_type in (Question.QuestionType.MCQ_SINGLE, Question.QuestionType.MCQ_MULTI):
            for index, option_text in enumerate(clean_options):
                if option_text:
                    QuestionOption.objects.create(
                        question=question,
                        option_text=option_text,
                        is_correct=str(index) in correct_options,
                        order=index + 1,
                    )

        for index, image in enumerate(request.FILES.getlist("question_images")):
            QuestionImage.objects.create(question=question, image=image, order=index + 1)

        messages.success(request, f"Question {next_question_number} saved successfully.")
        if action == "complete":
            return redirect("test_preview", assessment_id=assessment.id)
        return redirect("question_create", assessment_id=assessment.id)

    return render(
        request,
        "exam_engine/question_create.html",
        {
            "assessment": assessment,
            "question_number": next_question_number,
        }
    )


@login_required
def test_preview(request, assessment_id):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    assessment = Assessment.objects.filter(
        id=assessment_id,
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    ).first()

    if not assessment:
        messages.error(
            request,
            "Assessment not found or you do not have permission to view it."
        )

        return redirect("dashboard")

    if request.method == "POST":
        if request.POST.get("action") == "publish":
            if not assessment.questions.exists():
                messages.error(request, "Add at least one question before publishing this assessment.")
            else:
                assessment.is_published = True
                assessment.save(update_fields=["is_published"])
                messages.success(request, "Assessment published for students.")
        elif request.POST.get("action") == "unpublish":
            assessment.is_published = False
            assessment.save(update_fields=["is_published"])
            messages.success(request, "Assessment is no longer available to students.")
        elif request.POST.get("action") == "release_results":
            assessment.results_released = True
            assessment.save(update_fields=["results_released"])
            messages.success(request, "Results have been released to students.")
        elif request.POST.get("action") == "withhold_results":
            assessment.results_released = False
            assessment.save(update_fields=["results_released"])
            messages.success(request, "Results are now withheld from students.")
        return redirect("test_preview", assessment_id=assessment.id)

    questions = assessment.questions.prefetch_related(
        "options",
        "images"
    ).order_by(
        "order",
        "id"
    )

    calculated_total_marks = sum(
        question.marks
        for question in questions
    )

    return render(
        request,
        "exam_engine/test_preview.html",
        {
            "assessment": assessment,
            "questions": questions,
            "question_count": questions.count(),
            "calculated_total_marks": calculated_total_marks,
        }
    )


# =========================================================
# STUDENT - ASSESSMENT LIST
# =========================================================


@login_required
def student_assessments(request):

    if request.user.role != "STUDENT":
        return redirect("dashboard")

    student = request.user.student_profile

    if not student.student_class:

        return render(
            request,
            "exam_engine/student_assessments.html",
            {
                "assessments": [],
            }
        )

    assessments = Assessment.objects.filter(
        student_class=student.student_class,
        is_published=True,
    ).select_related(
        "subject",
        "teacher",
        "student_class"
    ).order_by(
        "due_date",
        "-created_at"
    )

    return render(
        request,
        "exam_engine/student_assessments.html",
        {
            "assessments": assessments,
        }
    )


# =========================================================
# STUDENT - TEST INSTRUCTIONS
# =========================================================


@login_required
def student_assessment_instructions(request, assessment_id):

    if request.user.role != "STUDENT":
        return redirect("dashboard")

    student = request.user.student_profile

    if not student.student_class:

        messages.error(
            request,
            "You are not assigned to a class."
        )

        return redirect("student_assessments")

    assessment = Assessment.objects.filter(
        id=assessment_id,
        student_class=student.student_class,
        is_published=True,
    ).select_related(
        "subject",
        "teacher",
        "student_class"
    ).first()

    if not assessment:

        messages.error(
            request,
            "Assessment not found or you do not have access to it."
        )

        return redirect("student_assessments")

    availability_error = _availability_error(assessment)
    if availability_error:
        messages.error(request, availability_error)
        return redirect("student_assessments")

    questions = assessment.questions.all()
    attempts = AssessmentAttempt.objects.filter(
        assessment=assessment, student=student
    )
    active_attempt = attempts.filter(
        status=AssessmentAttempt.Status.IN_PROGRESS
    ).first()
    attempt_count = attempts.count()
    limit_reached = (
        assessment.max_attempts > 0
        and attempt_count >= assessment.max_attempts
        and active_attempt is None
    )

    return render(
        request,
        "exam_engine/student_assessment_instructions.html",
        {
            "assessment": assessment,
            "question_count": questions.count(),
            "attempt_count": attempt_count,
            "active_attempt": active_attempt,
            "limit_reached": limit_reached,
            "requires_access_code": bool(assessment.access_code and active_attempt is None),
        }
    )


# =========================================================
# STUDENT - TAKE TEST
# =========================================================


@login_required
@transaction.atomic
def student_test(request, assessment_id):

    if request.user.role != "STUDENT":
        return redirect("dashboard")

    student = request.user.student_profile

    if not student.student_class:
        messages.error(
            request,
            "You are not assigned to a class."
        )
        return redirect("student_assessments")

    assessment = Assessment.objects.filter(
        id=assessment_id,
        student_class=student.student_class,
        is_published=True,
    ).first()

    if not assessment:
        messages.error(
            request,
            "Assessment not found or you do not have access to it."
        )
        return redirect("student_assessments")

    availability_error = _availability_error(assessment)
    if availability_error:
        existing_attempt = AssessmentAttempt.objects.filter(
            assessment=assessment,
            student=student,
            status=AssessmentAttempt.Status.IN_PROGRESS,
        ).order_by("-started_at", "-pk").first()
        if existing_attempt and assessment.due_date and timezone.now() > assessment.due_date:
            return redirect("student_submit", assessment_id=assessment.id)
        messages.error(request, availability_error)
        return redirect("student_assessments")

    questions = list(
        assessment.questions.prefetch_related(
            "options",
            "images"
        ).order_by(
            "order",
            "id"
        )
    )

    if not questions:
        messages.error(
            request,
            "This assessment does not have any questions yet."
        )
        return redirect(
            "student_assessment_instructions",
            assessment_id=assessment.id
        )

    # -------------------------------------------------
    # Resume an in-progress attempt or initialize a new one
    # -------------------------------------------------

    student_attempts = AssessmentAttempt.objects.filter(
        assessment=assessment, student=student
    )
    attempt = student_attempts.select_for_update().filter(
        status=AssessmentAttempt.Status.IN_PROGRESS
    ).order_by("-started_at", "-pk").first()
    created_attempt = False
    if attempt is None:
        attempt_count = student_attempts.count()
        if request.method == "POST" and not assessment.access_code:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": "There is no active attempt to save."}, status=403)
            return HttpResponseForbidden("There is no active attempt to update.")
        if assessment.max_attempts > 0 and attempt_count >= assessment.max_attempts:
            if request.method == "POST":
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"error": "No attempts remain."}, status=403)
                return HttpResponseForbidden("No attempts remain.")
            messages.error(request, "You have used all allowed attempts for this assessment.")
            if attempt_count:
                return redirect("student_result", assessment_id=assessment.id)
            return redirect("student_assessment_instructions", assessment_id=assessment.id)

        if assessment.access_code:
            if request.method != "POST":
                return render(request, "exam_engine/student_assessment_instructions.html", {
                    "assessment": assessment,
                    "question_count": len(questions),
                    "attempt_count": attempt_count,
                    "active_attempt": None,
                    "limit_reached": False,
                    "requires_access_code": True,
                })
            supplied_code = request.POST.get("access_code", "")
            if not hmac.compare_digest(supplied_code, assessment.access_code):
                messages.error(request, "The access code is incorrect.")
                return redirect("student_assessment_instructions", assessment_id=assessment.id)

        started_at = timezone.now()
        expires_at = None
        if assessment.timing_mode == Assessment.TimingMode.ENTIRE_TEST:
            expires_at = started_at + timedelta(
                hours=assessment.duration_hours,
                minutes=assessment.duration_minutes
            )
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=student,
            started_at=started_at,
            expires_at=expires_at,
            status=AssessmentAttempt.Status.IN_PROGRESS,
        )
        created_attempt = True

    if assessment.shuffle_questions:
        random.Random(f"study-pod-attempt-{attempt.pk}").shuffle(questions)

    if created_attempt and assessment.access_code:
        return redirect("student_test", assessment_id=assessment.id)

    # -------------------------------------------------
    # Do not allow completed attempts to reopen
    # -------------------------------------------------

    if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:
        if request.method == "POST":
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": "This attempt is no longer editable."}, status=403)
            return HttpResponseForbidden("This attempt is no longer editable.")
        messages.info(
            request,
            "This assessment has already been submitted."
        )
        return redirect(
            "student_result",
            assessment_id=assessment.id
        )

    # -------------------------------------------------
    # Check expiry
    #
    # We send expired attempts through student_submit
    # so all objective answers are graded correctly.
    # -------------------------------------------------

    if _attempt_expired(attempt):

        messages.warning(
            request,
            "Time is up. Your test has been automatically submitted."
        )

        return redirect(
            "student_submit",
            assessment_id=assessment.id
        )

    # -------------------------------------------------
    # Determine current question
    # -------------------------------------------------

    try:
        question_number = int(
            request.GET.get(
                "question",
                1
            )
        )
    except (TypeError, ValueError):
        question_number = 1

    question_number = max(
        1,
        min(question_number, len(questions))
    )

    question = questions[
        question_number - 1
    ]

    existing_answer, _ = StudentAnswer.objects.get_or_create(
        attempt=attempt,
        question=question,
    )
    if (
        assessment.timing_mode == Assessment.TimingMode.PER_QUESTION
        and existing_answer.question_expires_at is None
        and (question.time_limit_hours or question.time_limit_minutes)
    ):
        existing_answer.question_expires_at = timezone.now() + timedelta(
            hours=question.time_limit_hours,
            minutes=question.time_limit_minutes,
        )
        existing_answer.save(update_fields=["question_expires_at"])

    if (
        assessment.timing_mode == Assessment.TimingMode.PER_QUESTION
        and existing_answer.question_expires_at
        and timezone.now() >= existing_answer.question_expires_at
    ):
        messages.warning(request, "Time for this question has ended.")
        if question_number < len(questions):
            return redirect(
                f"{reverse('student_test', kwargs={'assessment_id': assessment.id})}?question={question_number + 1}"
            )
        return redirect("student_submit", assessment_id=assessment.id)

    # -------------------------------------------------
    # SAVE ANSWER + NAVIGATION
    # -------------------------------------------------

    if request.method == "POST":

        try:
            posted_question_number = int(
                request.POST.get(
                    "question_number",
                    question_number
                )
            )
        except (TypeError, ValueError):
            posted_question_number = question_number

        if (
            posted_question_number < 1
            or posted_question_number > len(questions)
        ):
            messages.error(
                request,
                "Invalid question."
            )
            return redirect(
                "student_test",
                assessment_id=assessment.id
            )

        question = questions[
            posted_question_number - 1
        ]

        question_answer = StudentAnswer.objects.filter(
            attempt=attempt,
            question=question,
        ).first()
        if (
            assessment.timing_mode == Assessment.TimingMode.PER_QUESTION
            and question_answer
            and question_answer.question_expires_at
            and timezone.now() >= question_answer.question_expires_at
        ):
            messages.warning(request, "Time for this question has ended.")
            if posted_question_number < len(questions):
                return redirect(
                    f"{reverse('student_test', kwargs={'assessment_id': assessment.id})}?question={posted_question_number + 1}"
                )
            return redirect("student_submit", assessment_id=assessment.id)

        # -------------------------------------------------
        # Check expiry again immediately before saving
        # -------------------------------------------------

        if _attempt_expired(attempt):

            messages.warning(
                request,
                "Time is up. Your test has been automatically submitted."
            )

            return redirect(
                "student_submit",
                assessment_id=assessment.id
            )

        # -------------------------------------------------
        # Read action
        # -------------------------------------------------

        action = request.POST.get(
            "action",
            "next"
        )

        # -------------------------------------------------
        # Read answer
        # -------------------------------------------------

        selected_option = None
        selected_options = []
        answer_text = ""

        if question.question_type == Question.QuestionType.MCQ_SINGLE:

            option_id = request.POST.get(
                "answer"
            )

            if option_id:
                selected_option = question.options.filter(
                    id=option_id
                ).first()

        elif question.question_type == Question.QuestionType.MCQ_MULTI:

            option_ids = request.POST.getlist(
                "answer"
            )

            selected_options = list(
                question.options.filter(
                    id__in=option_ids
                )
            )

        else:

            answer_text = request.POST.get(
                "answer",
                ""
            ).strip()

        # -------------------------------------------------
        # Mark for review
        #
        # The template sends:
        # mark_for_review=true
        # when the current question should be marked.
        # -------------------------------------------------

        mark_for_review = (
            request.POST.get("mark_for_review") == "true"
        )

        # -------------------------------------------------
        # Create / update StudentAnswer
        # -------------------------------------------------

        student_answer, created_answer = (
            StudentAnswer.objects.get_or_create(
                attempt=attempt,
                question=question
            )
        )

        student_answer.selected_option = selected_option
        student_answer.answer_text = answer_text
        student_answer.is_marked_for_review = mark_for_review
        student_answer.save()

        # -------------------------------------------------
        # Multiple-choice answers
        # -------------------------------------------------

        if question.question_type == Question.QuestionType.MCQ_MULTI:

            student_answer.selected_options.set(
                selected_options
            )

        else:

            student_answer.selected_options.clear()

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"saved": True})

        # -------------------------------------------------
        # Mark / Unmark for review
        #
        # This action saves the answer and stays on the
        # same question.
        # -------------------------------------------------

        if action == "review":

            student_answer.is_marked_for_review = (
                not student_answer.is_marked_for_review
            )

            student_answer.save(
                update_fields=["is_marked_for_review"]
            )

            return redirect(
                f"{reverse('student_test', kwargs={'assessment_id': assessment.id})}"
                f"?question={posted_question_number}"
            )

        # -------------------------------------------------
        # Jump to a question
        # -------------------------------------------------

        if action == "jump":

            try:
                target_question = int(
                    request.POST.get(
                        "target_question",
                        1
                    )
                )
            except (TypeError, ValueError):
                target_question = 1

            target_question = max(
                1,
                min(target_question, len(questions))
            )

            return redirect(
                f"{reverse('student_test', kwargs={'assessment_id': assessment.id})}"
                f"?question={target_question}"
            )

        # -------------------------------------------------
        # Previous question
        # -------------------------------------------------

        if action == "previous":

            previous_question = max(
                1,
                posted_question_number - 1
            )

            return redirect(
                f"{reverse('student_test', kwargs={'assessment_id': assessment.id})}"
                f"?question={previous_question}"
            )

        # -------------------------------------------------
        # Submit test
        # -------------------------------------------------

        if action == "submit":

            return redirect(
                "student_submit",
                assessment_id=assessment.id
            )

        # -------------------------------------------------
        # Next question
        # -------------------------------------------------

        if action == "next":

            next_question_number = (
                posted_question_number + 1
            )

            if next_question_number <= len(questions):

                return redirect(
                    f"{reverse('student_test', kwargs={'assessment_id': assessment.id})}"
                    f"?question={next_question_number}"
                )

            return redirect(
                "student_submit",
                assessment_id=assessment.id
            )

        # Fallback
        return redirect(
            f"{reverse('student_test', kwargs={'assessment_id': assessment.id})}"
            f"?question={posted_question_number}"
        )

    # -------------------------------------------------
    # Load current answer
    # -------------------------------------------------

    existing_answer = StudentAnswer.objects.filter(
        attempt=attempt,
        question=question
    ).prefetch_related(
        "selected_options"
    ).first()

    # -------------------------------------------------
    # Load all saved answers for question navigator
    # -------------------------------------------------

    saved_answers = list(
        StudentAnswer.objects.filter(
            attempt=attempt
        ).prefetch_related(
            "selected_options"
        )
    )

    answer_map = {
        answer.question_id: answer
        for answer in saved_answers
    }

    # -------------------------------------------------
    # Build question navigator
    # -------------------------------------------------

    question_navigation = []

    for index, nav_question in enumerate(
        questions,
        start=1
    ):

        nav_answer = answer_map.get(
            nav_question.id
        )

        is_answered = False
        is_marked = False

        if nav_answer:

            is_marked = (
                nav_answer.is_marked_for_review
            )

            if (
                nav_question.question_type
                == Question.QuestionType.MCQ_SINGLE
            ):

                is_answered = (
                    nav_answer.selected_option_id
                    is not None
                )

            elif (
                nav_question.question_type
                == Question.QuestionType.MCQ_MULTI
            ):

                is_answered = bool(
                    list(
                        nav_answer.selected_options.all()
                    )
                )

            else:

                is_answered = bool(
                    nav_answer.answer_text.strip()
                )

        question_navigation.append(
            {
                "number": index,
                "question_id": nav_question.id,
                "answered": is_answered,
                "marked": is_marked,
                "current": index == question_number,
            }
        )

    # -------------------------------------------------
    # Render
    # -------------------------------------------------

    return render(
        request,
        "exam_engine/student_test.html",
        {
            "assessment": assessment,
            "attempt": attempt,
            "question": question,
            "question_number": question_number,
            "question_count": len(questions),
            "existing_answer": existing_answer,
            "question_navigation": question_navigation,
            "timer_deadline": (
                existing_answer.question_expires_at
                if assessment.timing_mode == Assessment.TimingMode.PER_QUESTION
                else attempt.expires_at
            ),
        }
    )


# =========================================================
# STUDENT - SUBMIT TEST
# =========================================================


@login_required
@transaction.atomic
def student_submit(request, assessment_id):

    if request.user.role != "STUDENT":
        return redirect("dashboard")

    student = request.user.student_profile

    if not student.student_class:
        messages.error(
            request,
            "You are not assigned to a class."
        )
        return redirect("student_assessments")

    assessment = Assessment.objects.filter(
        id=assessment_id,
        student_class=student.student_class
    ).first()

    if not assessment:
        messages.error(
            request,
            "Assessment not found or you do not have access to it."
        )
        return redirect("student_assessments")

    attempt = AssessmentAttempt.objects.select_for_update().filter(
        assessment=assessment,
        student=student,
        status=AssessmentAttempt.Status.IN_PROGRESS,
    ).order_by("-started_at", "-pk").first()

    if attempt is None:
        attempt = AssessmentAttempt.objects.select_for_update().filter(
            assessment=assessment,
            student=student,
        ).order_by("-started_at", "-pk").first()

    if not attempt:
        messages.error(
            request,
            "No test attempt was found."
        )
        return redirect("student_assessments")

    # Do not submit the same attempt twice.
    if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:

        return redirect(
            "student_result",
            assessment_id=assessment.id
        )

    # -------------------------------------------------
    # Determine whether this was a time-expired submit
    # -------------------------------------------------

    now = timezone.now()
    time_expired = (
        _attempt_expired(attempt, now)
        or (assessment.due_date is not None and now > assessment.due_date)
    )

    questions = assessment.questions.prefetch_related(
        "options"
    ).order_by(
        "order",
        "id"
    )

    total_awarded = Decimal("0")
    correct_count = 0
    incorrect_count = 0
    unanswered_count = 0
    pending_manual_count = 0

    for question in questions:

        answer = StudentAnswer.objects.filter(
            attempt=attempt,
            question=question
        ).prefetch_related(
            "selected_options"
        ).select_related(
            "selected_option"
        ).first()

        if not answer:
            answer = StudentAnswer.objects.create(
                attempt=attempt,
                question=question,
                awarded_marks=(
                    Decimal("0")
                    if question.question_type == Question.QuestionType.SHORT_ANSWER
                    else None
                ),
            )
            if question.question_type != Question.QuestionType.SHORT_ANSWER:
                unanswered_count += 1
                continue

        # -------------------------------------------------
        # MCQ - Single
        # -------------------------------------------------

        if question.question_type == Question.QuestionType.MCQ_SINGLE:

            if not answer.selected_option:

                unanswered_count += 1
                answer.awarded_marks = Decimal("0")
                answer.save(
                    update_fields=["awarded_marks"]
                )
                continue

            if answer.selected_option.is_correct:

                answer.awarded_marks = Decimal(
                    str(question.marks)
                )

                total_awarded += answer.awarded_marks
                correct_count += 1

            else:

                if question.negative_marking:

                    answer.awarded_marks = -Decimal(
                        str(question.negative_marks)
                    )

                    total_awarded += answer.awarded_marks

                else:

                    answer.awarded_marks = Decimal("0")

                incorrect_count += 1

            answer.save(
                update_fields=["awarded_marks"]
            )

        # -------------------------------------------------
        # MCQ - Multiple
        # -------------------------------------------------

        elif question.question_type == Question.QuestionType.MCQ_MULTI:

            selected_ids = set(
                answer.selected_options.values_list(
                    "id",
                    flat=True
                )
            )

            correct_ids = set(
                question.options.filter(
                    is_correct=True
                ).values_list(
                    "id",
                    flat=True
                )
            )

            if not selected_ids:

                unanswered_count += 1
                answer.awarded_marks = Decimal("0")

            elif selected_ids == correct_ids:

                answer.awarded_marks = Decimal(
                    str(question.marks)
                )

                total_awarded += answer.awarded_marks
                correct_count += 1

            else:

                if question.negative_marking:

                    answer.awarded_marks = -Decimal(
                        str(question.negative_marks)
                    )

                    total_awarded += answer.awarded_marks

                else:

                    answer.awarded_marks = Decimal("0")

                incorrect_count += 1

            answer.save(
                update_fields=["awarded_marks"]
            )

        # -------------------------------------------------
        # True / False
        # -------------------------------------------------

        elif question.question_type == Question.QuestionType.TRUE_FALSE:

            if not answer.answer_text:

                unanswered_count += 1
                answer.awarded_marks = Decimal("0")

            elif (
                answer.answer_text.strip().lower()
                ==
                question.correct_answer.strip().lower()
            ):

                answer.awarded_marks = Decimal(
                    str(question.marks)
                )

                total_awarded += answer.awarded_marks
                correct_count += 1

            else:

                if question.negative_marking:

                    answer.awarded_marks = -Decimal(
                        str(question.negative_marks)
                    )

                    total_awarded += answer.awarded_marks

                else:

                    answer.awarded_marks = Decimal("0")

                incorrect_count += 1

            answer.save(
                update_fields=["awarded_marks"]
            )

        # -------------------------------------------------
        # Numerical
        # -------------------------------------------------

        elif question.question_type == Question.QuestionType.NUMERICAL:

            if not answer.answer_text:

                unanswered_count += 1
                answer.awarded_marks = Decimal("0")

            elif (
                answer.answer_text.strip()
                ==
                question.correct_answer.strip()
            ):

                answer.awarded_marks = Decimal(
                    str(question.marks)
                )

                total_awarded += answer.awarded_marks
                correct_count += 1

            else:

                if question.negative_marking:

                    answer.awarded_marks = -Decimal(
                        str(question.negative_marks)
                    )

                    total_awarded += answer.awarded_marks

                else:

                    answer.awarded_marks = Decimal("0")

                incorrect_count += 1

            answer.save(
                update_fields=["awarded_marks"]
            )

        # -------------------------------------------------
        # Short Answer
        # -------------------------------------------------

        elif question.question_type == Question.QuestionType.SHORT_ANSWER:

            if not answer.answer_text.strip():

                unanswered_count += 1
                answer.awarded_marks = Decimal("0")

            else:

                # Short answers require teacher evaluation.
                answer.awarded_marks = None
                pending_manual_count += 1

            answer.save(
                update_fields=["awarded_marks"]
            )

    # -------------------------------------------------
    # Mark attempt as submitted / time expired
    # -------------------------------------------------

    if pending_manual_count:

        attempt.status = AssessmentAttempt.Status.NEEDS_EVALUATION

    elif assessment.questions.filter(
        question_type=Question.QuestionType.SHORT_ANSWER
    ).exists() and not time_expired:

        attempt.status = AssessmentAttempt.Status.EVALUATED

    elif time_expired:

        attempt.status = (
            AssessmentAttempt.Status.TIME_EXPIRED
        )

    else:

        attempt.status = (
            AssessmentAttempt.Status.SUBMITTED
        )

    attempt.submitted_at = timezone.now()

    attempt.save(
        update_fields=[
            "status",
            "submitted_at"
        ]
    )

    if time_expired:

        if pending_manual_count:
            messages.warning(
                request,
                "Your assessment was submitted and is waiting for teacher evaluation."
            )
        else:
            messages.warning(
                request,
                "Your time expired. The assessment has been submitted."
            )

    else:

        if pending_manual_count:
            messages.info(
                request,
                "Your assessment was submitted and is waiting for teacher evaluation."
            )
        else:
            messages.success(
                request,
                "Your assessment has been submitted successfully."
            )

    return redirect(
        "student_result",
        assessment_id=assessment.id
    )


# =========================================================
# STUDENT - RESULT
# =========================================================


@login_required
def student_result(request, assessment_id):

    if request.user.role != "STUDENT":
        return redirect("dashboard")

    student = request.user.student_profile

    if not student.student_class:
        messages.error(
            request,
            "You are not assigned to a class."
        )
        return redirect("student_assessments")

    assessment = Assessment.objects.filter(
        id=assessment_id,
        student_class=student.student_class
    ).first()

    if not assessment:
        messages.error(
            request,
            "Assessment not found."
        )
        return redirect("student_assessments")

    attempt = AssessmentAttempt.objects.filter(
        assessment=assessment,
        student=student
    ).order_by("-started_at", "-pk").first()

    if not attempt:
        return redirect("student_assessments")

    if not assessment.show_results_immediately and not assessment.results_released:
        return render(request, "exam_engine/student_result.html", {
            "assessment": assessment,
            "attempt": attempt,
            "results_pending": True,
        })

    answers = attempt.answers.select_related(
        "question",
        "selected_option"
    ).prefetch_related(
        "selected_options",
        "question__options"
    ).order_by(
        "question__order",
        "question__id"
    )

    total_marks = Decimal(
        str(assessment.total_marks)
    )

    score = attempt.score
    percentage = attempt.percentage
    passed = percentage >= Decimal(str(assessment.passmark_percentage))

    correct_count = 0
    incorrect_count = 0
    unanswered_count = 0
    pending_manual_count = 0

    for answer in answers:

        question = answer.question

        if (
            question.question_type
            == Question.QuestionType.SHORT_ANSWER
        ):

            if answer.answer_text.strip():
                if answer.awarded_marks is None:
                    pending_manual_count += 1
                elif answer.awarded_marks > 0:
                    correct_count += 1
                else:
                    incorrect_count += 1

            else:

                unanswered_count += 1

        elif (
            not answer.answer_text
            and not answer.selected_option
            and not answer.selected_options.exists()
        ):

            unanswered_count += 1

        elif answer.awarded_marks is not None:

            if answer.awarded_marks > 0:

                correct_count += 1

            elif answer.awarded_marks < 0:

                incorrect_count += 1

            else:

                incorrect_count += 1

    return render(
        request,
        "exam_engine/student_result.html",
        {
            "assessment": assessment,
            "attempt": attempt,
            "answers": answers,
            "score": score,
            "total_marks": total_marks,
            "percentage": percentage,
            "passed": passed,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "unanswered_count": unanswered_count,
            "pending_manual_count": pending_manual_count,
        }
    )


# =========================================================
# TEACHER - STUDENT ATTEMPTS
# =========================================================


@login_required
def teacher_attempts(request, assessment_id):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    # Only the teacher who owns the assessment can see
    # its student attempts.
    assessment = Assessment.objects.filter(
        id=assessment_id,
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    ).first()

    if not assessment:
        messages.error(
            request,
            "Assessment not found or you do not have permission to view it."
        )
        return redirect("test_management")

    attempts = list(
        AssessmentAttempt.objects.filter(
            assessment=assessment
        ).select_related(
            "student",
            "student__user"
        ).order_by(
            "-started_at"
        )
    )

    # -------------------------------------------------
    # Add score information to each attempt
    # -------------------------------------------------

    for attempt in attempts:
        attempt.display_score = attempt.score
        attempt.display_percentage = attempt.percentage

    return render(
        request,
        "exam_engine/teacher_attempts.html",
        {
            "assessment": assessment,
            "attempts": attempts,
        }
    )


# =========================================================
# TEACHER - ATTEMPT DETAIL
# =========================================================


@login_required
def teacher_attempt_detail(
    request,
    assessment_id,
    attempt_id
):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    # -------------------------------------------------
    # Security: teacher must own the assessment
    # -------------------------------------------------

    assessment = Assessment.objects.filter(
        id=assessment_id,
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    ).first()

    if not assessment:

        messages.error(
            request,
            "Assessment not found or you do not have permission to view it."
        )

        return redirect(
            "test_management"
        )

    # -------------------------------------------------
    # Get attempt
    # -------------------------------------------------

    attempt = AssessmentAttempt.objects.filter(
        id=attempt_id,
        assessment=assessment
    ).select_related(
        "assessment",
        "student",
        "student__user"
    ).first()

    if not attempt:

        messages.error(
            request,
            "Attempt not found."
        )

        return redirect(
            "teacher_attempts",
            assessment_id=assessment.id
        )

    grading_errors = []
    submitted_values = {}
    if request.method == "POST":
        pending_answers = list(
            StudentAnswer.objects.filter(
                attempt=attempt,
                question__question_type=Question.QuestionType.SHORT_ANSWER,
                awarded_marks__isnull=True,
            ).exclude(answer_text="").select_related("question")
        )

        if attempt.status == AssessmentAttempt.Status.IN_PROGRESS:
            grading_errors.append("This assessment attempt has not been submitted yet.")
        elif not pending_answers:
            grading_errors.append("There are no short answers waiting for evaluation.")
        else:
            grades = []
            for answer in pending_answers:
                marks_key = f"marks_awarded_{answer.id}"
                feedback_key = f"teacher_feedback_{answer.id}"
                raw_marks = (request.POST.get(marks_key) or "").strip()
                submitted_values[marks_key] = raw_marks
                submitted_values[feedback_key] = request.POST.get(feedback_key, "")

                try:
                    marks_awarded = Decimal(raw_marks)
                    if not marks_awarded.is_finite():
                        raise InvalidOperation
                except (InvalidOperation, TypeError, ValueError):
                    grading_errors.append(
                        f"Enter a valid mark for Question {answer.question.order}."
                    )
                    continue

                if marks_awarded < 0 or marks_awarded > Decimal(str(answer.question.marks)):
                    grading_errors.append(
                        f"Marks for Question {answer.question.order} must be between 0 and {answer.question.marks}."
                    )
                    continue
                if marks_awarded.as_tuple().exponent < -2:
                    grading_errors.append(
                        f"Marks for Question {answer.question.order} can have at most two decimal places."
                    )
                    continue

                grades.append((answer, marks_awarded, submitted_values[feedback_key]))

            if not grading_errors and len(grades) == len(pending_answers):
                with transaction.atomic():
                    for answer, marks_awarded, feedback in grades:
                        answer.awarded_marks = marks_awarded
                        answer.teacher_feedback = feedback.strip()
                        answer.save(update_fields=["awarded_marks", "teacher_feedback"])

                    attempt.refresh_from_db()
                    attempt.status = (
                        AssessmentAttempt.Status.NEEDS_EVALUATION
                        if attempt.pending_evaluation_count
                        else AssessmentAttempt.Status.EVALUATED
                    )
                    attempt.save(update_fields=["status"])

                messages.success(request, "Evaluation saved and the attempt score has been updated.")
                return redirect(
                    "teacher_attempt_detail",
                    assessment_id=assessment.id,
                    attempt_id=attempt.id,
                )

    answers = StudentAnswer.objects.filter(
        attempt=attempt
    ).select_related(
        "question",
        "selected_option"
    ).prefetch_related(
        "selected_options",
        "question__options"
    ).order_by(
        "question__order",
        "question__id"
    )

    for answer in answers:
        answer.needs_evaluation = (
            answer.question.question_type == Question.QuestionType.SHORT_ANSWER
            and bool(answer.answer_text.strip())
            and answer.awarded_marks is None
        )
        answer.grading_marks_value = submitted_values.get(
            f"marks_awarded_{answer.id}",
            answer.awarded_marks if answer.awarded_marks is not None else "",
        )
        answer.grading_feedback_value = submitted_values.get(
            f"teacher_feedback_{answer.id}",
            answer.teacher_feedback,
        )

    # -------------------------------------------------
    # Calculate attempt summary
    # -------------------------------------------------

    score = attempt.score

    total_marks = Decimal(
        str(assessment.total_marks)
    )

    percentage = attempt.percentage

    correct_count = 0
    incorrect_count = 0
    unanswered_count = 0
    pending_manual_count = 0

    for answer in answers:

        question = answer.question

        if (
            question.question_type
            == Question.QuestionType.SHORT_ANSWER
        ):

            if answer.answer_text.strip():

                if answer.awarded_marks is None:
                    pending_manual_count += 1

                elif answer.awarded_marks > 0:
                    correct_count += 1

                else:
                    incorrect_count += 1

            else:

                unanswered_count += 1

        elif (
            not answer.answer_text
            and not answer.selected_option
            and not answer.selected_options.exists()
        ):

            unanswered_count += 1

        elif answer.awarded_marks is not None:

            if answer.awarded_marks > 0:

                correct_count += 1

            else:

                incorrect_count += 1

    return render(
        request,
        "exam_engine/teacher_attempt_detail.html",
        {
            "attempt": attempt,
            "assessment": assessment,
            "answers": answers,
            "score": score,
            "total_marks": total_marks,
            "percentage": percentage,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "unanswered_count": unanswered_count,
            "pending_manual_count": pending_manual_count,
            "grading_errors": grading_errors,
            "submitted_values": submitted_values,
        }
    )
