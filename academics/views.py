from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile

from .forms import AttendanceSelectionForm, DoubtReplyForm, DoubtThreadForm
from .models import Attendance, Class, DoubtReply, DoubtThread, Subject, TeachingAssignment


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
