from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
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


# =========================================================
# TEACHER
# =========================================================


@login_required
def test_management(request):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    assessments = Assessment.objects.filter(
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    ).order_by("-created_at")

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

    # Automatically determine the next question number.
    next_question_number = (
        assessment.questions.count() + 1
    )

    if request.method == "POST":

        action = request.POST.get(
            "action",
            "next"
        )

        question_text = request.POST.get(
            "question_text"
        )

        question_type = request.POST.get(
            "question_type"
        )

        marks = request.POST.get(
            "marks"
        )

        negative_marks = request.POST.get(
            "negative_marks"
        )

        negative_marking = (
            request.POST.get("negative_marking") == "on"
        )

        # Per-question timing
        time_limit_hours = request.POST.get(
            "time_limit_hours"
        ) or 0

        time_limit_minutes = request.POST.get(
            "time_limit_minutes"
        ) or 0

        if not all([
            question_text,
            question_type,
            marks,
        ]):

            messages.error(
                request,
                "Please fill in all required fields."
            )

            return redirect(
                "question_create",
                assessment_id=assessment.id
            )

        # If timing is not per-question,
        # do not store question-level timing.
        if assessment.timing_mode != Assessment.TimingMode.PER_QUESTION:

            time_limit_hours = 0
            time_limit_minutes = 0

        # Automatically assign question number.
        question = Question.objects.create(
            assessment=assessment,
            question_text=question_text,
            question_type=question_type,
            marks=marks,
            negative_marking=negative_marking,
            negative_marks=negative_marks or 0,
            time_limit_hours=time_limit_hours,
            time_limit_minutes=time_limit_minutes,
            order=next_question_number,
        )

        # -------------------------------------------------
        # Save MCQ options
        # -------------------------------------------------

        if question_type in [
            Question.QuestionType.MCQ_SINGLE,
            Question.QuestionType.MCQ_MULTI,
        ]:

            option_texts = request.POST.getlist(
                "option_text"
            )

            correct_options = request.POST.getlist(
                "correct_option"
            )

            for index, option_text in enumerate(
                option_texts
            ):

                if not option_text.strip():
                    continue

                is_correct = (
                    str(index) in correct_options
                )

                QuestionOption.objects.create(
                    question=question,
                    option_text=option_text,
                    is_correct=is_correct,
                    order=index + 1,
                )

        # -------------------------------------------------
        # Save True / False answer
        # -------------------------------------------------

        elif question_type == Question.QuestionType.TRUE_FALSE:

            correct_answer = request.POST.get(
                "true_false_answer",
                ""
            )

            question.correct_answer = correct_answer

            question.save(
                update_fields=["correct_answer"]
            )

        # -------------------------------------------------
        # Save Numerical answer
        # -------------------------------------------------

        elif question_type == Question.QuestionType.NUMERICAL:

            correct_answer = request.POST.get(
                "numerical_answer",
                ""
            )

            question.correct_answer = correct_answer

            question.save(
                update_fields=["correct_answer"]
            )

        # -------------------------------------------------
        # Save Short Answer
        # -------------------------------------------------

        elif question_type == Question.QuestionType.SHORT_ANSWER:

            correct_answer = request.POST.get(
                "short_answer",
                ""
            )

            question.correct_answer = correct_answer

            question.save(
                update_fields=["correct_answer"]
            )

        # -------------------------------------------------
        # Save question images
        # -------------------------------------------------

        uploaded_images = request.FILES.getlist(
            "question_images"
        )

        for index, image in enumerate(
            uploaded_images
        ):

            QuestionImage.objects.create(
                question=question,
                image=image,
                order=index + 1,
            )

        messages.success(
            request,
            f"Question {next_question_number} saved successfully."
        )

        # -------------------------------------------------
        # Complete Test Making
        # -------------------------------------------------

        if action == "complete":

            return redirect(
                "test_preview",
                assessment_id=assessment.id
            )

        # -------------------------------------------------
        # Save & Next Question
        # -------------------------------------------------

        return redirect(
            "question_create",
            assessment_id=assessment.id
        )

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
        student_class=student.student_class
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
        student_class=student.student_class
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

    questions = assessment.questions.all()

    return render(
        request,
        "exam_engine/student_assessment_instructions.html",
        {
            "assessment": assessment,
            "question_count": questions.count(),
        }
    )


# =========================================================
# STUDENT - TAKE TEST
# =========================================================


@login_required
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
        student_class=student.student_class
    ).first()

    if not assessment:
        messages.error(
            request,
            "Assessment not found or you do not have access to it."
        )
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
    # Get or create student's attempt
    # -------------------------------------------------

    attempt, created = AssessmentAttempt.objects.get_or_create(
        assessment=assessment,
        student=student,
        defaults={
            "started_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(
                hours=assessment.duration_hours,
                minutes=assessment.duration_minutes
            ),
            "status": AssessmentAttempt.Status.IN_PROGRESS,
        }
    )

    # -------------------------------------------------
    # Do not allow completed attempts to reopen
    # -------------------------------------------------

    if attempt.status != AssessmentAttempt.Status.IN_PROGRESS:
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

    if timezone.now() >= attempt.expires_at:

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

        # -------------------------------------------------
        # Check expiry again immediately before saving
        # -------------------------------------------------

        if timezone.now() >= attempt.expires_at:

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
        }
    )


# =========================================================
# STUDENT - SUBMIT TEST
# =========================================================


@login_required
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

    attempt = AssessmentAttempt.objects.filter(
        assessment=assessment,
        student=student
    ).first()

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

    time_expired = (
        timezone.now() >= attempt.expires_at
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
                answer.awarded_marks = None

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

    if time_expired:

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

        messages.warning(
            request,
            "Your time expired. The assessment has been submitted."
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
    ).first()

    if not attempt:
        return redirect("student_assessments")

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

    awarded_answers = [
        answer
        for answer in answers
        if answer.awarded_marks is not None
    ]

    score = sum(
        (
            answer.awarded_marks
            for answer in awarded_answers
        ),
        Decimal("0")
    )

    if total_marks > 0:

        percentage = (
            score / total_marks
        ) * Decimal("100")

    else:

        percentage = Decimal("0")

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

                pending_manual_count += 1

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

        awarded_answers = list(
            StudentAnswer.objects.filter(
                attempt=attempt,
                awarded_marks__isnull=False
            )
        )

        attempt.display_score = sum(
            (
                answer.awarded_marks
                for answer in awarded_answers
            ),
            Decimal("0")
        )

        total_marks = Decimal(
            str(assessment.total_marks)
        )

        if total_marks > 0:

            attempt.display_percentage = (
                attempt.display_score
                / total_marks
            ) * Decimal("100")

        else:

            attempt.display_percentage = Decimal("0")

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

    # -------------------------------------------------
    # Calculate attempt summary
    # -------------------------------------------------

    score = sum(
        (
            answer.awarded_marks
            for answer in answers
            if answer.awarded_marks is not None
        ),
        Decimal("0")
    )

    total_marks = Decimal(
        str(assessment.total_marks)
    )

    if total_marks > 0:

        percentage = (
            score / total_marks
        ) * Decimal("100")

    else:

        percentage = Decimal("0")

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
        }
    )
