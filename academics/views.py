from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile

from .forms import AttendanceSelectionForm
from .models import Attendance, Class


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
