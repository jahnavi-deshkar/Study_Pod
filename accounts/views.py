import logging

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST

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

logger = logging.getLogger(__name__)


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
            if user.is_staff or user.is_superuser:
                return render(
                    request,
                    "accounts/login.html",
                    {"error": "Admin accounts must sign in through the Django administration portal."},
                )
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
            request.FILES,
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
    from academics.views import teacher_attendance

    return teacher_attendance(request)


@login_required
def student_attendance(request):
    from academics.views import student_attendance

    return student_attendance(request)


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
        return HttpResponseForbidden("Only teachers can upload study resources.")

    teacher = request.user.teacher_profile

    assignments = TeachingAssignment.objects.filter(
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    )
    past_uploads = Resource.objects.filter(
        teacher=teacher
    ).select_related(
        "student_class",
        "subject",
    ).order_by("-created_at")

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

        return redirect("resource_upload")

    return render(
        request,
        "accounts/resource_upload.html",
        {
            "assignments": assignments,
            "past_uploads": past_uploads,
        }
    )


@login_required
def resource_list(request):
    user = request.user
    past_uploads = Resource.objects.none()

    if user.role == "TEACHER":

        past_uploads = Resource.objects.filter(
            teacher=user.teacher_profile
        ).select_related(
            "student_class",
            "subject"
        ).order_by(
            "-created_at"
        )
        resources = past_uploads

        # ChromaDB status is read only for the teacher's own resource library.
        # A failure to open the local index should not make the page unavailable.
        from ai_suggestions.services.vector_store import StudyPodVectorStore

        try:
            vector_store = StudyPodVectorStore()
        except Exception:
            vector_store = None

        for resource in past_uploads:
            if vector_store is None:
                resource.indexing_status = "unknown"
                continue
            try:
                resource.indexing_status = (
                    "indexed" if vector_store.is_resource_indexed(resource.pk)
                    else "not_indexed"
                )
            except Exception:
                resource.indexing_status = "unknown"

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

    elif user.role == "PARENT":
        children = user.parent_profile.students.filter(
            student_class__isnull=False
        ).values_list("student_class_id", flat=True)
        resources = Resource.objects.filter(
            student_class_id__in=children
        ).select_related("teacher", "student_class", "subject").order_by("-created_at")

    else:
        resources = Resource.objects.none()

    return render(
        request,
        "accounts/resource_list.html",
        {
            "resources": resources,
            "past_uploads": past_uploads,
        }
    )


@login_required
def teacher_resource_detail(request, resource_id):
    if request.user.role != "TEACHER":
        return HttpResponseForbidden("Teacher access is required.")

    teacher = getattr(request.user, "teacher_profile", None)
    if teacher is None:
        return HttpResponseForbidden("Teacher profile was not found.")

    resource = get_object_or_404(
        Resource.objects.select_related("student_class", "subject", "teacher"),
        pk=resource_id,
        teacher=teacher,
    )

    try:
        from ai_suggestions.services.vector_store import StudyPodVectorStore

        indexed = StudyPodVectorStore().is_resource_indexed(resource.pk)
        indexing_status = "indexed" if indexed else "not_indexed"
    except Exception:
        indexing_status = "unknown"

    return render(
        request,
        "accounts/resource_detail.html",
        {"resource": resource, "indexing_status": indexing_status},
    )


@login_required
def student_resource_detail(request, resource_id):
    if request.user.role != "STUDENT":
        return HttpResponseForbidden("Student access is required.")

    student = getattr(request.user, "student_profile", None)
    if student is None or student.student_class_id is None:
        return HttpResponseForbidden("A student class is required to view this resource.")

    resource = get_object_or_404(
        Resource.objects.select_related("student_class", "subject", "teacher__user"),
        pk=resource_id,
        student_class_id=student.student_class_id,
    )
    filename = resource.file.name.lower() if resource.file else ""
    is_pdf = filename.endswith(".pdf")
    is_image = filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))

    try:
        from ai_suggestions.services.vector_store import StudyPodVectorStore

        indexed = StudyPodVectorStore().is_resource_indexed(resource.pk)
        indexing_status = "indexed" if indexed else "not_indexed"
    except Exception:
        indexing_status = "unknown"

    return render(
        request,
        "accounts/student_resource_detail.html",
        {
            "resource": resource,
            "is_pdf": is_pdf,
            "is_image": is_image,
            "indexing_status": indexing_status,
        },
    )


@login_required
@require_POST
def teacher_resource_reindex(request, resource_id):
    if request.user.role != "TEACHER":
        return HttpResponseForbidden("Teacher access is required.")

    teacher = getattr(request.user, "teacher_profile", None)
    if teacher is None:
        return HttpResponseForbidden("Teacher profile was not found.")

    resource = get_object_or_404(
        Resource.objects.select_related("student_class", "subject"),
        pk=resource_id,
        teacher=teacher,
    )

    try:
        if not resource.file:
            raise ValueError("This resource has no uploaded file.")

        from ai_suggestions.services.vector_store import StudyPodVectorStore

        chunks = StudyPodVectorStore().ingest_resource(
            resource_id=resource.pk,
            file_path=resource.file.path,
            metadata={
                "class_id": resource.student_class_id,
                "subject": resource.subject.name,
                "subject_id": resource.subject_id,
                "teacher_id": teacher.pk,
                "title": resource.title,
            },
        )
        if chunks:
            messages.success(request, f"Resource is ready for AI search ({chunks} text sections prepared).")
        else:
            messages.warning(
                request,
                "No readable text was found in this file. Check that it contains selectable text, then try again.",
            )
    except ValueError as exc:
        logger.warning("Resource %s could not be prepared for AI search: %s", resource.pk, exc)
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Could not prepare resource %s for AI search.", resource.pk)
        messages.error(
            request,
            "Could not prepare this resource for AI search. Check that the file is readable and AI services are installed.",
        )

    return redirect("teacher_resource_detail", resource_id=resource.pk)


@login_required
@require_POST
def teacher_resource_delete(request, resource_id):
    if request.user.role != "TEACHER":
        return HttpResponseForbidden("Teacher access is required.")

    teacher = getattr(request.user, "teacher_profile", None)
    if teacher is None:
        return HttpResponseForbidden("Teacher profile was not found.")

    resource = get_object_or_404(Resource, pk=resource_id, teacher=teacher)
    resource_id = resource.pk

    try:
        from ai_suggestions.services.vector_store import StudyPodVectorStore

        StudyPodVectorStore().delete_resource(resource_id)
    except Exception:
        # Continue deletion if the local vector index is unavailable.
        pass

    if resource.file:
        resource.file.delete(save=False)
    resource.delete()
    messages.success(request, "Resource deleted.")
    return redirect("resource_list")


@login_required
def create_assessment(request, workflow_type=None):

    if request.user.role != "TEACHER":
        return redirect("dashboard")

    teacher = request.user.teacher_profile

    if workflow_type is None:
        if request.method == "POST":
            request.session.pop("assessment_timing", None)
            selected_type = request.POST.get("assessment_type")
            route_name = {
                "ASSIGNMENT": "create_assignment",
                "TEST": "create_test",
            }.get(selected_type)
            if route_name:
                return redirect(route_name)
            messages.error(request, "Choose Assignment or Test to continue.")
        return render(request, "accounts/assessment_type_choice.html")

    assignments = TeachingAssignment.objects.filter(
        teacher=teacher
    ).select_related(
        "student_class",
        "subject"
    )

    if workflow_type == "TEST":
        if request.method == "POST":
            title = (request.POST.get("title") or "").strip()
            student_class_id = request.POST.get("student_class")
            subject_id = request.POST.get("subject")
            try:
                total_marks = int(request.POST.get("total_marks", ""))
                if total_marks < 1:
                    raise ValueError
            except (TypeError, ValueError):
                total_marks = None

            valid_assignment = assignments.filter(
                student_class_id=student_class_id,
                subject_id=subject_id,
            ).exists()
            if not title or not valid_assignment or total_marks is None:
                messages.error(
                    request,
                    "Enter a title, choose a class and subject you teach, and set total marks above zero.",
                )
                return render(
                    request,
                    "accounts/create_test_assessment.html",
                    {"assignments": assignments},
                )

            assessment = Assessment.objects.create(
                title=title,
                teacher=teacher,
                student_class_id=student_class_id,
                subject_id=subject_id,
                assessment_type=Assessment.AssessmentType.TEST,
                total_marks=total_marks,
                workflow_status=Assessment.WorkflowStatus.DRAFT,
                is_published=False,
            )
            messages.success(request, "Test draft created. Add its questions below.")
            return redirect("question_create", assessment_id=assessment.id)

        return render(
            request,
            "accounts/create_test_assessment.html",
            {"assignments": assignments},
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

            return redirect("create_assignment")

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

                return redirect("create_assignment")

            if duration_minutes > 59:

                messages.error(
                    request,
                    "Minutes must be between 0 and 59."
                )

                return redirect("create_assignment")

        # Store timing information temporarily.
        request.session["assessment_timing"] = {
            "timing_mode": timing_mode,
            "duration_hours": duration_hours,
            "duration_minutes": duration_minutes,
        }

        return redirect("create_assignment")


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

            return redirect("create_assignment")

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

        try:
            total_marks = int(request.POST.get("total_marks", ""))
            if total_marks < 1:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Total marks must be a positive whole number.")
            return redirect("create_assignment")

        available_from = request.POST.get(
            "available_from"
        )

        due_date = request.POST.get(
            "due_date"
        )

        try:
            max_attempts = int(request.POST.get("max_attempts", "1"))
            if max_attempts < 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Maximum attempts must be zero (unlimited) or a positive whole number.")
            return redirect("create_assignment")

        try:
            passmark_percentage = float(request.POST.get("passmark_percentage", "40"))
            if not 0 <= passmark_percentage <= 100:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Passmark must be between 0 and 100 percent.")
            return redirect("create_assignment")

        if not all([
            title,
            student_class_id,
            subject_id,
            total_marks,
        ]):

            messages.error(
                request,
                "Please fill in all required fields."
            )

            return redirect("create_assignment")


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

            return redirect("create_assignment")


        # -------------------------------------------------
        # Create assessment
        # -------------------------------------------------

        assessment = Assessment.objects.create(
            title=title,
            description=description,
            teacher=teacher,
            student_class_id=student_class_id,
            subject_id=subject_id,
            assessment_type=Assessment.AssessmentType.ASSIGNMENT,
            total_marks=total_marks,
            workflow_status=Assessment.WorkflowStatus.DRAFT,
            is_published=False,

            timing_mode=timing_data["timing_mode"],

            duration_hours=timing_data[
                "duration_hours"
            ],

            duration_minutes=timing_data[
                "duration_minutes"
            ],

            available_from=available_from or None,
            due_date=due_date or None,
            max_attempts=max_attempts,
            shuffle_questions=request.POST.get("shuffle_questions") == "on",
            show_results_immediately=request.POST.get("show_results_immediately", "on") == "on",
            passmark_percentage=passmark_percentage,
            access_code=None,
            instructions=(request.POST.get("instructions") or "").strip(),
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
