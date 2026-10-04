from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile
from exam_engine.models import AssessmentAttempt, Question, StudentAnswer

from .forms import AttendanceSelectionForm, DoubtReplyForm, DoubtThreadForm
from .models import Assessment, Attendance, Class, DoubtReply, DoubtThread, Subject, TeachingAssignment, Timetable


WEEKDAYS = tuple(Timetable.DayOfWeek.choices)


def _timetable_days(entries):
    by_day = {code: [] for code, _label in WEEKDAYS}
    for entry in entries:
        by_day[entry.day_of_week].append(entry)
    return [
        {"code": code, "label": label, "entries": by_day[code]}
        for code, label in WEEKDAYS
    ]


@login_required
def teacher_timetable(request):
    if request.user.role != "TEACHER":
        return redirect("dashboard")
    teacher = request.user.teacher_profile
    entries = list(
        Timetable.objects.filter(teacher=teacher)
        .filter(
            student_class__teaching_assignments__teacher=teacher,
            student_class__teaching_assignments__subject=models.F("subject"),
        )
        .select_related("student_class", "subject", "teacher__user")
        .distinct()
    )
    return render(request, "academics/teacher_timetable.html", {
        "days": _timetable_days(entries),
    })


@login_required
def student_timetable(request):
    if request.user.role != "STUDENT":
        return redirect("dashboard")
    student_class = request.user.student_profile.student_class
    entries = list(
        Timetable.objects.filter(student_class=student_class)
        .select_related("student_class", "subject", "teacher__user")
    ) if student_class else []
    return render(request, "academics/student_timetable.html", {
        "days": _timetable_days(entries),
        "student_class": student_class,
    })


def _attendance_context(selection_form, selected_class=None, selected_date=None,
                        students=None, attendance_errors=None):
    return {
        "selection_form": selection_form,
        "selected_class": selected_class,
        "selected_date": selected_date,
        "students": students or [],
        "attendance_errors": attendance_errors or [],
        "status_choices": Attendance.Status.choices,
    }


@login_required
def teacher_attendance(request):
    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile
    assigned_classes = Class.objects.filter(
        teaching_assignments__teacher=teacher
    ).distinct()

    form_data = request.POST if request.method == "POST" else (request.GET or None)
    selection_form = AttendanceSelectionForm(
        form_data,
        teacher=teacher,
        initial={"date": timezone.localdate()},
    )
    students = []
    selected_class = None
    selected_date = None
    attendance_errors = []

    action = request.POST.get("action") if request.method == "POST" else None
    if request.method == "POST" and action not in ("load", "save"):
        return HttpResponseBadRequest("Invalid attendance action.")

    if selection_form.is_bound and selection_form.is_valid():
        selected_class = selection_form.cleaned_data["student_class"]
        selected_date = selection_form.cleaned_data["date"]
        students = list(
            StudentProfile.objects.filter(student_class=selected_class)
            .select_related("user")
            .order_by("user__last_name", "user__first_name", "roll_number")
        )

        records = {
            record.student_id: record
            for record in Attendance.objects.filter(
                student__in=students,
                date=selected_date,
            )
        }
        for student in students:
            record = records.get(student.id)
            submitted_status = request.POST.get(f"status_{student.id}") if request.method == "POST" else None
            submitted_remarks = request.POST.get(f"remarks_{student.id}") if request.method == "POST" else None
            student.attendance_status = submitted_status or (record.status if record else "")
            student.attendance_remarks = submitted_remarks if submitted_remarks is not None else (record.remarks if record else "")

        if action == "save":
            valid_statuses = {value for value, _label in Attendance.Status.choices}
            roster_ids = {student.id for student in students}
            statuses = {}
            for student in students:
                value = request.POST.get(f"status_{student.id}", "")
                if student.id not in roster_ids or value not in valid_statuses:
                    attendance_errors.append(
                        f"Select Present, Absent, or Late for {student.user.get_full_name() or student.user.username}."
                    )
                else:
                    statuses[student.id] = value

            if not attendance_errors:
                to_create = []
                to_update = []
                for student in students:
                    status = statuses[student.id]
                    remarks = (request.POST.get(f"remarks_{student.id}") or "").strip()
                    record = records.get(student.id)
                    if record is None:
                        to_create.append(Attendance(
                            student=student,
                            student_class=selected_class,
                            date=selected_date,
                            status=status,
                            is_present=status == Attendance.Status.PRESENT,
                            remarks=remarks,
                            marked_by=teacher,
                        ))
                    else:
                        record.student_class = selected_class
                        record.status = status
                        record.is_present = status == Attendance.Status.PRESENT
                        record.remarks = remarks
                        record.marked_by = teacher
                        to_update.append(record)

                with transaction.atomic():
                    if to_create:
                        Attendance.objects.bulk_create(to_create)
                    if to_update:
                        Attendance.objects.bulk_update(
                            to_update,
                            ["student_class", "status", "is_present", "remarks", "marked_by"],
                        )

                messages.success(request, "Attendance saved successfully.")
                return redirect(
                    f"{reverse('teacher_attendance')}?student_class={selected_class.pk}&date={selected_date.isoformat()}"
                )

    elif request.method == "POST":
        raw_class_id = request.POST.get("student_class")
        if raw_class_id and not assigned_classes.filter(pk=raw_class_id).exists():
            return HttpResponseForbidden("You are not assigned to this class.")
    elif request.method == "GET":
        raw_class_id = request.GET.get("student_class")
        if raw_class_id and not assigned_classes.filter(pk=raw_class_id).exists():
            return HttpResponseForbidden("You are not assigned to this class.")

    return render(
        request,
        "academics/teacher_attendance.html",
        _attendance_context(
            selection_form,
            selected_class=selected_class,
            selected_date=selected_date,
            students=students,
            attendance_errors=attendance_errors,
        ),
    )


@login_required
def student_attendance(request):
    if request.user.role != "STUDENT":
        return redirect("dashboard")

    student = request.user.student_profile
    records = Attendance.objects.filter(student=student).select_related(
        "student_class", "marked_by", "marked_by__user"
    ).order_by("-date", "-id")

    total_classes = records.count()
    present_days = records.filter(status=Attendance.Status.PRESENT).count()
    absent_or_late_days = total_classes - present_days
    attendance_percentage = (present_days / total_classes * 100) if total_classes else 0

    return render(
        request,
        "academics/student_attendance.html",
        {
            "records": records,
            "total_classes": total_classes,
            "present_days": present_days,
            "absent_or_late_days": absent_or_late_days,
            "attendance_percentage": attendance_percentage,
        },
    )


def _forum_scope(user):
    """Return classes visible to this user and whether they are a student."""
    if user.role == "STUDENT":
        profile = getattr(user, "student_profile", None)
        if profile and profile.student_class_id:
            return Class.objects.filter(pk=profile.student_class_id), True
        return Class.objects.none(), True
    if user.role == "TEACHER":
        profile = getattr(user, "teacher_profile", None)
        if profile:
            return Class.objects.filter(
                teaching_assignments__teacher=profile
            ).distinct(), False
    return Class.objects.none(), False


def _teacher_can_access_thread(user, thread):
    profile = getattr(user, "teacher_profile", None)
    return bool(profile and TeachingAssignment.objects.filter(
        teacher=profile,
        student_class=thread.student_class,
        subject=thread.subject,
    ).exists())


@login_required
def doubt_threads(request):
    classes, is_student = _forum_scope(request.user)
    if not classes.exists():
        return HttpResponseForbidden("You do not have access to a class discussion forum.")

    raw_class = request.POST.get("student_class") or request.GET.get("student_class")
    selected_class = classes.filter(pk=raw_class).first() if raw_class else classes.first()
    if raw_class and selected_class is None:
        return HttpResponseForbidden("You are not assigned to this class.")

    thread_form = DoubtThreadForm(
        request.POST if request.method == "POST" else None,
        student_class=selected_class,
    )
    if request.method == "POST":
        if not is_student:
            return HttpResponseForbidden("Only students can start a doubt thread.")
        if selected_class and thread_form.is_valid():
            thread = thread_form.save(commit=False)
            thread.student = request.user.student_profile
            thread.student_class = selected_class
            thread.save()
            messages.success(request, "Your question has been posted.")
            return redirect("doubt_thread_detail", pk=thread.pk)

    subject_id = request.GET.get("subject", "")
    status = request.GET.get("status", "OPEN").upper()
    query = request.GET.get("q", "").strip()
    allowed_subjects = Subject.objects.filter(
        teaching_assignments__student_class=selected_class
    )
    if not is_student:
        allowed_subjects = allowed_subjects.filter(
            teaching_assignments__teacher=request.user.teacher_profile
        )
    allowed_subjects = allowed_subjects.distinct()
    threads = DoubtThread.objects.filter(student_class=selected_class).select_related(
        "student__user", "subject"
    )
    if not is_student:
        threads = threads.filter(subject__in=allowed_subjects)
    if subject_id:
        threads = threads.filter(subject_id=subject_id)
    if status == "OPEN":
        threads = threads.filter(status=DoubtThread.Status.OPEN)
    elif status == "RESOLVED":
        threads = threads.filter(status=DoubtThread.Status.RESOLVED)
    elif status != "ALL":
        status = "OPEN"
        threads = threads.filter(status=DoubtThread.Status.OPEN)
    if query:
        threads = threads.filter(models.Q(title__icontains=query) | models.Q(content__icontains=query))
    return render(request, "academics/doubt_threads.html", {
        "classes": classes.order_by("name", "section"),
        "selected_class": selected_class,
        "subjects": allowed_subjects.order_by("name"),
        "selected_subject": subject_id,
        "status_filter": status,
        "search_query": query,
        "threads": threads,
        "thread_form": thread_form,
        "can_create_thread": is_student,
    })


@login_required
def doubt_thread_detail(request, pk):
    classes, is_student = _forum_scope(request.user)
    thread = get_object_or_404(
        DoubtThread.objects.select_related("student__user", "student_class", "subject"),
        pk=pk,
    )
    if not classes.filter(pk=thread.student_class_id).exists():
        return HttpResponseForbidden("You cannot access this class discussion.")
    assigned_teacher = not is_student and _teacher_can_access_thread(request.user, thread)
    if not is_student and not assigned_teacher:
        return HttpResponseForbidden("You are not assigned to this subject.")
    is_author = is_student and thread.student.user_id == request.user.pk
    reply_form = DoubtReplyForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        action = request.POST.get("action", "reply")
        if action == "resolve":
            if not (is_author or assigned_teacher):
                return HttpResponseForbidden("Only the author or assigned subject teacher can resolve this question.")
            thread.status = (
                DoubtThread.Status.RESOLVED
                if thread.status == DoubtThread.Status.OPEN
                else DoubtThread.Status.OPEN
            )
            thread.save(update_fields=["status"])
            messages.success(request, f"Question marked {thread.get_status_display().lower()}.")
            return redirect("doubt_thread_detail", pk=thread.pk)
        if action != "reply":
            return HttpResponseBadRequest("Invalid discussion action.")
        if thread.status == DoubtThread.Status.RESOLVED:
            messages.error(request, "This question is resolved and no longer accepts replies.")
        elif reply_form.is_valid():
            reply = reply_form.save(commit=False)
            reply.thread = thread
            reply.user = request.user
            reply.is_teacher_reply = assigned_teacher
            reply.save()
            messages.success(request, "Your reply has been posted.")
            return redirect("doubt_thread_detail", pk=thread.pk)

    return render(request, "academics/doubt_thread_detail.html", {
        "thread": thread,
        "replies": thread.replies.select_related("user"),
        "reply_form": reply_form,
        "can_resolve": is_author or assigned_teacher,
        "can_reply": thread.status == DoubtThread.Status.OPEN,
        "is_teacher": assigned_teacher,
    })


@login_required
def student_analytics(request):
    if request.user.role != "STUDENT":
        return HttpResponseForbidden("Student analytics are available only to the signed-in student.")

    student = request.user.student_profile
    submitted_attempts = AssessmentAttempt.objects.filter(
        student=student,
        submitted_at__isnull=False,
    ).select_related("assessment__subject", "assessment__student_class")
    taken_stats = submitted_attempts.aggregate(
        taken=Count("pk"),
        total_available=Sum("assessment__total_marks"),
    )
    obtained = StudentAnswer.objects.filter(
        attempt__in=submitted_attempts,
    ).aggregate(total=Sum("awarded_marks"))["total"] or Decimal("0")
    total_available = taken_stats["total_available"] or 0
    average_percentage = (
        (Decimal(obtained) / Decimal(total_available) * Decimal("100"))
        if total_available else Decimal("0")
    )

    if student.student_class_id:
        assigned_stats = Assessment.objects.filter(
            student_class_id=student.student_class_id,
            is_published=True,
        ).aggregate(count=Count("pk"))
        subject_ids = submitted_attempts.values_list(
            "assessment__subject_id", flat=True
        ).distinct()
    else:
        assigned_stats = {"count": 0}
        subject_ids = Subject.objects.none().values_list("pk", flat=True)

    subject_breakdown = []
    for subject in Subject.objects.filter(pk__in=subject_ids).order_by("name"):
        subject_attempts = submitted_attempts.filter(assessment__subject=subject)
        stats = subject_attempts.aggregate(
            taken=Count("pk"),
            available=Sum("assessment__total_marks"),
        )
        marks = StudentAnswer.objects.filter(
            attempt__in=subject_attempts,
        ).aggregate(total=Sum("awarded_marks"))["total"] or Decimal("0")
        available = stats["available"] or 0
        percentage = Decimal(marks) / Decimal(available) * Decimal("100") if available else Decimal("0")
        subject_breakdown.append({
            "subject": subject,
            "assessments_taken": stats["taken"],
            "obtained_marks": marks,
            "total_marks": available,
            "percentage": percentage,
        })

    highest_subject = max(subject_breakdown, key=lambda row: row["percentage"], default=None)
    lowest_subject = min(subject_breakdown, key=lambda row: row["percentage"], default=None)
    history = []
    for attempt in submitted_attempts.annotate(
        analytics_score=Coalesce(
            Sum("answers__awarded_marks"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=9, decimal_places=2),
        )
    ).order_by("-submitted_at", "-pk"):
        total = attempt.assessment.total_marks
        history.append({
            "attempt": attempt,
            "score": attempt.analytics_score,
            "total_marks": total,
            "percentage": (Decimal(attempt.analytics_score) / Decimal(total) * 100) if total else Decimal("0"),
        })

    return render(request, "academics/student_analytics.html", {
        "taken_count": taken_stats["taken"],
        "assigned_count": assigned_stats["count"],
        "average_percentage": average_percentage,
        "subject_breakdown": subject_breakdown,
        "highest_subject": highest_subject,
        "lowest_subject": lowest_subject,
        "history": history,
    })


@login_required
def teacher_analytics(request):
    if request.user.role != "TEACHER":
        return HttpResponseForbidden("Teacher analytics are available only to teachers.")

    teacher = request.user.teacher_profile
    assignments = TeachingAssignment.objects.filter(teacher=teacher).select_related(
        "student_class", "subject"
    )
    assigned_classes = Class.objects.filter(
        teaching_assignments__teacher=teacher
    ).distinct().order_by("name", "section")
    raw_class_id = request.GET.get("student_class")
    if raw_class_id:
        selected_class = assigned_classes.filter(pk=raw_class_id).first()
        if selected_class is None:
            return HttpResponseForbidden("You are not assigned to this class.")
    else:
        selected_class = assigned_classes.first()

    assessments = Assessment.objects.none()
    selected_assessment = None
    if selected_class:
        assigned_subjects = assignments.filter(
            student_class=selected_class
        ).values_list("subject_id", flat=True)
        assessments = Assessment.objects.filter(
            teacher=teacher,
            student_class=selected_class,
            subject_id__in=assigned_subjects,
        ).select_related("subject", "student_class").order_by("-created_at")
        raw_assessment_id = request.GET.get("assessment")
        if raw_assessment_id:
            selected_assessment = assessments.filter(pk=raw_assessment_id).first()
            if selected_assessment is None:
                return HttpResponseForbidden("This assessment is not assigned to your class.")

    threshold_value = request.GET.get("threshold", "50")
    try:
        threshold = Decimal(threshold_value)
        if not threshold.is_finite() or threshold < 0 or threshold > 100:
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        threshold = Decimal("50")
        threshold_value = "50"

    context = {
        "assigned_classes": assigned_classes,
        "selected_class": selected_class,
        "assessments": assessments,
        "selected_assessment": selected_assessment,
        "threshold": threshold,
        "threshold_value": threshold_value,
    }
    if selected_assessment:
        total_marks = selected_assessment.total_marks or 0
        score_field = DecimalField(max_digits=9, decimal_places=2)
        percentage_expression = ExpressionWrapper(
            F("analytics_score") * Value(Decimal("100")) / Value(Decimal(total_marks or 1)),
            output_field=DecimalField(max_digits=9, decimal_places=2),
        )
        submitted_attempts = AssessmentAttempt.objects.filter(
            assessment=selected_assessment,
            submitted_at__isnull=False,
        ).select_related("student__user").annotate(
            analytics_score=Coalesce(
                Sum("answers__awarded_marks"),
                Value(Decimal("0.00")),
                output_field=score_field,
            ),
        ).annotate(analytics_percentage=percentage_expression)
        attempt_stats = submitted_attempts.aggregate(
            submissions=Count("pk"),
            average_percentage=Avg("analytics_percentage"),
            highest_score=Max("analytics_score"),
            lowest_score=Min("analytics_score"),
        )
        enrolled_count = StudentProfile.objects.filter(
            student_class=selected_class
        ).count()

        questions = selected_assessment.questions.annotate(
            submitted_count=Count(
                "student_answers",
                filter=Q(student_answers__attempt__submitted_at__isnull=False),
                distinct=True,
            ),
            correct_count=Count(
                "student_answers",
                filter=Q(
                    student_answers__attempt__submitted_at__isnull=False,
                    student_answers__awarded_marks__gte=F("marks"),
                ),
                distinct=True,
            ),
        ).order_by("order", "pk")
        item_analysis = []
        for question in questions:
            correct_percentage = (
                Decimal(question.correct_count) / Decimal(attempt_stats["submissions"]) * 100
                if attempt_stats["submissions"] else Decimal("0")
            )
            item_analysis.append({
                "question": question,
                "submitted_count": question.submitted_count,
                "correct_count": question.correct_count,
                "correct_percentage": correct_percentage,
                "high_error": correct_percentage < 40,
            })

        needs_attention = submitted_attempts.filter(
            analytics_percentage__lt=threshold
        ).order_by("analytics_percentage", "student__user__last_name", "student__user__first_name")
        context.update({
            "average_percentage": attempt_stats["average_percentage"] or Decimal("0"),
            "highest_score": attempt_stats["highest_score"],
            "lowest_score": attempt_stats["lowest_score"],
            "submissions": attempt_stats["submissions"],
            "enrolled_count": enrolled_count,
            "item_analysis": item_analysis,
            "needs_attention": needs_attention,
        })
    return render(request, "academics/teacher_analytics.html", context)
