from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect

from .forms import (
    NoticeForm,
    UserProfileForm,
    TeacherProfileForm,
    StudentProfileForm,
    ParentProfileForm,
)

from academics.models import (
    Notice,
    Class,
    Attendance,
    TeachingAssignment,
    Resource,
    Assessment,
    Subject,
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
        return render(
            request,
            "accounts/teacher_dashboard.html"
        )

    if request.user.role == "STUDENT":
        return render(
            request,
            "accounts/student_dashboard.html"
        )

    if request.user.role == "PARENT":
        return render(
            request,
            "accounts/parent_dashboard.html"
        )

    return redirect("login")


@login_required
def profile(request):
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
        user_form = UserProfileForm(
            request.POST,
            instance=user
        )

        profile_form = profile_form_class(
            request.POST,
            instance=profile_object
        )

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()

            return redirect("profile")

    else:
        user_form = UserProfileForm(
            instance=user
        )

        profile_form = profile_form_class(
            instance=profile_object
        )

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

            notice = form.save(
                commit=False
            )

            notice.teacher = teacher
            notice.save()

            messages.success(
                request,
                "Notice created successfully."
            )

            return redirect("notices")

    else:

        form = NoticeForm(
            teacher=teacher
        )

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
        student_class_id = request.POST.get(
            "student_class"
        )
        selected_date = request.POST.get(
            "date"
        )

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

        existing_records = Attendance.objects.filter(
            student__in=students,
            date=selected_date
        )

        attendance_status = {
            record.student_id: record.is_present
            for record in existing_records
        }

        for student in students:

            if student.id in attendance_status:

                if attendance_status[student.id]:
                    student.attendance_status = "present"
                else:
                    student.attendance_status = "absent"

            else:
                student.attendance_status = ""

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


# ============================================================
# STUDY RESOURCES
# ============================================================

@login_required
def resource_upload(request):
    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    assignments = TeachingAssignment.objects.filter(
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    )

    # Allow the teacher to change the timing selection.
    if request.GET.get("change_timing") == "1":
        request.session.pop(
            "assessment_timing",
            None
        )
        return redirect("create_assessment")

    if request.method == "POST":

        title = request.POST.get(
            "title",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        student_class_id = request.POST.get(
            "student_class"
        )

        subject_id = request.POST.get(
            "subject"
        )

        uploaded_file = request.FILES.get(
            "file"
        )

        if not title:
            messages.error(
                request,
                "Please enter a resource title."
            )

            return redirect("resource_upload")

        if not student_class_id:
            messages.error(
                request,
                "Please select a class."
            )

            return redirect("resource_upload")

        if not subject_id:
            messages.error(
                request,
                "Please select a subject."
            )

            return redirect("resource_upload")

        if not uploaded_file:
            messages.error(
                request,
                "Please select a file."
            )

            return redirect("resource_upload")

        assignment_exists = TeachingAssignment.objects.filter(
            teacher=teacher,
            student_class_id=student_class_id,
            subject_id=subject_id
        ).exists()

        if not assignment_exists:
            messages.error(
                request,
                "You are not assigned to this class and subject."
            )

            return redirect("resource_upload")

        student_class = Class.objects.get(
            id=student_class_id
        )

        subject = Subject.objects.get(
            id=subject_id
        )

        Resource.objects.create(
            title=title,
            description=description,
            teacher=teacher,
            student_class=student_class,
            subject=subject,
            file=uploaded_file,
        )

        messages.success(
            request,
            "Resource uploaded successfully."
        )

        return redirect(
            "resource_list"
        )

    return render(
        request,
        "accounts/resource_upload.html",
        {
            "assignments": assignments,
        }
    )


@login_required
def resource_list(request):
    user = request.user

    if user.role == "TEACHER":

        resources = Resource.objects.filter(
            teacher=user.teacher_profile
        ).select_related(
            "student_class",
            "subject"
        ).order_by(
            "-created_at"
        )

    elif user.role == "STUDENT":

        student = user.student_profile

        if student.student_class:

            resources = Resource.objects.filter(
                student_class=student.student_class
            ).select_related(
                "teacher",
                "student_class",
                "subject"
            ).order_by(
                "-created_at"
            )

        else:
            resources = Resource.objects.none()

    else:
        resources = Resource.objects.none()

    return render(
        request,
        "accounts/resource_list.html",
        {
            "resources": resources,
        }
    )

@login_required
def create_assessment(request):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    assignments = TeachingAssignment.objects.filter(
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    )

    # -------------------------------------------------
    # Stage 1:
    # Choose test timing
    # -------------------------------------------------

    if request.method == "POST" and request.POST.get("stage") == "timing":

        timing_mode = request.POST.get(
            "timing_mode"
        )

        if timing_mode not in [
            Assessment.TimingMode.NONE,
            Assessment.TimingMode.ENTIRE_TEST,
            Assessment.TimingMode.PER_QUESTION,
        ]:

            messages.error(
                request,
                "Please select a valid timing option."
            )

            return redirect("create_assessment")

        duration_hours = 0
        duration_minutes = 0

        # ---------------------------------------------
        # Entire test timing
        # ---------------------------------------------

        if timing_mode == Assessment.TimingMode.ENTIRE_TEST:

            duration_hours = int(
                request.POST.get(
                    "duration_hours",
                    0
                ) or 0
            )

            duration_minutes = int(
                request.POST.get(
                    "duration_minutes",
                    0
                ) or 0
            )

            if (
                duration_hours == 0
                and duration_minutes == 0
            ):

                messages.error(
                    request,
                    "Please enter a time limit for the entire test."
                )

                return redirect("create_assessment")

            if duration_minutes > 59:

                messages.error(
                    request,
                    "Minutes must be between 0 and 59."
                )

                return redirect("create_assessment")

        # Store timing information temporarily.
        request.session["assessment_timing"] = {
            "timing_mode": timing_mode,
            "duration_hours": duration_hours,
            "duration_minutes": duration_minutes,
        }

        return redirect("create_assessment")


    # -------------------------------------------------
    # Stage 2:
    # Create the assessment
    # -------------------------------------------------

    if request.method == "POST" and request.POST.get("stage") == "details":

        timing_data = request.session.get(
            "assessment_timing"
        )

        if not timing_data:

            messages.error(
                request,
                "Please select the test timing first."
            )

            return redirect("create_assessment")

        title = request.POST.get("title")

        description = request.POST.get(
            "description"
        )

        student_class_id = request.POST.get(
            "student_class"
        )

        subject_id = request.POST.get(
            "subject"
        )

        assessment_type = request.POST.get(
            "assessment_type"
        )

        total_marks = request.POST.get(
            "total_marks"
        )

        available_from = request.POST.get(
            "available_from"
        )

        due_date = request.POST.get(
            "due_date"
        )

        if not all([
            title,
            student_class_id,
            subject_id,
            assessment_type,
            total_marks,
        ]):

            messages.error(
                request,
                "Please fill in all required fields."
            )

            return redirect("create_assessment")


        # -------------------------------------------------
        # Verify teacher assignment
        # -------------------------------------------------

        valid_assignment = assignments.filter(
            student_class_id=student_class_id,
            subject_id=subject_id
        ).exists()

        if not valid_assignment:

            messages.error(
                request,
                "You are not assigned to this class and subject."
            )

            return redirect("create_assessment")


        # -------------------------------------------------
        # Create assessment
        # -------------------------------------------------

        assessment = Assessment.objects.create(
            title=title,
            description=description,
            teacher=teacher,
            student_class_id=student_class_id,
            subject_id=subject_id,
            assessment_type=assessment_type,
            total_marks=total_marks,

            timing_mode=timing_data["timing_mode"],

            duration_hours=timing_data[
                "duration_hours"
            ],

            duration_minutes=timing_data[
                "duration_minutes"
            ],

            available_from=available_from or None,
            due_date=due_date or None,
        )


        # Timing information is no longer needed
        # in the session after creating the assessment.

        request.session.pop(
            "assessment_timing",
            None
        )


        messages.success(
            request,
            "Assessment created successfully."
        )


        return redirect(
            "question_create",
            assessment_id=assessment.id
        )


    # -------------------------------------------------
    # Display the correct stage
    # -------------------------------------------------

    timing_data = request.session.get(
        "assessment_timing"
    )


    return render(
        request,
        "accounts/create_assessment.html",
        {
            "assignments": assignments,
            "timing_data": timing_data,
        }
    )