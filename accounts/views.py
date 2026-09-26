from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import NoticeForm
from academics.models import Notice, Class, Attendance
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from .forms import (
    UserProfileForm,
    TeacherProfileForm,
    StudentProfileForm,
    ParentProfileForm,
)

def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("dashboard")

        return render(
            request,
            "accounts/login.html",
            {"error": "Invalid username or password."}
        )

    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")

def dashboard(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role == "TEACHER":
        return render(request, "accounts/teacher_dashboard.html")

    if request.user.role == "STUDENT":
        return render(request, "accounts/student_dashboard.html")

    if request.user.role == "PARENT":
        return render(request, "accounts/parent_dashboard.html")

    return redirect("login")

def profile(request):
    if not request.user.is_authenticated:
        return redirect("login")

    user = request.user

    if user.role == "TEACHER":
        profile_object = user.teacher_profile
        profile_form_class = TeacherProfileForm

    elif user.role == "STUDENT":
        profile_object = user.student_profile
        profile_form_class = StudentProfileForm

    elif user.role == "PARENT":
        profile_object = user.parent_profile
        profile_form_class = ParentProfileForm

    else:
        return redirect("dashboard")

    if request.method == "POST":
        user_form = UserProfileForm(request.POST, instance=user)
        profile_form = profile_form_class(
            request.POST,
            instance=profile_object
        )

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()

            return redirect("profile")

    else:
        user_form = UserProfileForm(instance=user)
        profile_form = profile_form_class(instance=profile_object)

    return render(
        request,
        "accounts/profile.html",
        {
            "user_form": user_form,
            "profile_form": profile_form,
        }
    )
@login_required
def notices(request):
    user = request.user

    if user.role == "TEACHER":
        notice_list = Notice.objects.filter(
            teacher=user.teacher_profile
        ).select_related(
            "student_class"
        ).order_by("-created_at")

    elif user.role == "STUDENT":
        student = user.student_profile

        if student.student_class:
            notice_list = Notice.objects.filter(
                student_class=student.student_class
            ).select_related(
                "teacher",
                "student_class"
            ).order_by("-created_at")
        else:
            notice_list = Notice.objects.none()

    elif user.role == "PARENT":
        notice_list = Notice.objects.filter(
            student_class__students__parent=user.parent_profile
        ).select_related(
            "teacher",
            "student_class"
        ).distinct().order_by("-created_at")

    else:
        notice_list = Notice.objects.none()

    return render(
        request,
        "accounts/notices.html",
        {"notices": notice_list}
    )


@login_required
def create_notice(request):
    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    if request.method == "POST":
        form = NoticeForm(
            request.POST,
            request.FILES,
            teacher=teacher
        )

        if form.is_valid():
            notice = form.save(commit=False)
            notice.teacher = teacher
            notice.save()

            messages.success(
                request,
                "Notice created successfully."
            )

            return redirect("notices")

    else:
        form = NoticeForm(teacher=teacher)

    return render(
        request,
        "accounts/create_notice.html",
        {"form": form}
    )
@login_required
def attendance(request):
    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    assigned_classes = Class.objects.filter(
        teaching_assignments__teacher=teacher
    ).distinct()

    selected_class = None
    students = []
    selected_date = ""

    if request.method == "POST":

        action = request.POST.get("action")
        student_class_id = request.POST.get("student_class")
        selected_date = request.POST.get("date")

        if not student_class_id or not selected_date:
            messages.error(
                request,
                "Please select a class and date."
            )

            return redirect("attendance")

        selected_class = Class.objects.get(
            id=student_class_id
        )

        students = list(
            selected_class.students.all()
        )

        # Load previously saved attendance
        existing_records = Attendance.objects.filter(
            student__in=students,
            date=selected_date
        )

        attendance_status = {
            record.student_id: record.is_present
            for record in existing_records
        }

        # Attach attendance status to each student
        for student in students:

            if student.id in attendance_status:

                if attendance_status[student.id]:
                    student.attendance_status = "present"
                else:
                    student.attendance_status = "absent"

            else:
                student.attendance_status = ""

        # Save attendance
        if action == "save":

            for student in students:

                status = request.POST.get(
                    f"student_{student.id}"
                )

                Attendance.objects.update_or_create(
                    student=student,
                    date=selected_date,
                    defaults={
                        "is_present": status == "present",
                        "marked_by": teacher,
                    }
                )

            messages.success(
                request,
                "Attendance saved successfully."
            )

            return redirect("attendance")

    return render(
        request,
        "accounts/attendance.html",
        {
            "classes": assigned_classes,
            "students": students,
            "selected_class": selected_class,
            "selected_date": selected_date,
        }
    )
@login_required
def student_attendance(request):
    if request.user.role != "STUDENT":
        return redirect("dashboard")

    student = request.user.student_profile

    records = Attendance.objects.filter(
        student=student
    ).order_by("-date")

    total_days = records.count()

    present_days = records.filter(
        is_present=True
    ).count()

    if total_days > 0:
        attendance_percentage = (
            present_days / total_days
        ) * 100
    else:
        attendance_percentage = 0

    return render(
        request,
        "accounts/student_attendance.html",
        {
            "records": records,
            "total_days": total_days,
            "present_days": present_days,
            "attendance_percentage": attendance_percentage,
        }
    )
@login_required
def parent_attendance(request):
    if request.user.role != "PARENT":
        return redirect("dashboard")

    parent = request.user.parent_profile

    students = parent.students.all()

    student_data = []

    for student in students:

        records = Attendance.objects.filter(
            student=student
        ).order_by("-date")

        total_days = records.count()

        present_days = records.filter(
            is_present=True
        ).count()

        if total_days > 0:
            attendance_percentage = (
                present_days / total_days
            ) * 100
        else:
            attendance_percentage = 0

        student_data.append({
            "student": student,
            "records": records,
            "total_days": total_days,
            "present_days": present_days,
            "attendance_percentage": attendance_percentage,
        })

    return render(
        request,
        "accounts/parent_attendance.html",
        {
            "student_data": student_data,
        }
    )