from django.db import models
from django.core.validators import FileExtensionValidator
from .storage import PrivateDoubtAttachmentStorage


class Class(models.Model):
    name = models.CharField(max_length=50)
    section = models.CharField(max_length=10)
    academic_year = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.name} - {self.section}"


class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class TeachingAssignment(models.Model):
    teacher = models.ForeignKey(
        "accounts.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="teaching_assignments"
    )

    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="teaching_assignments"
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="teaching_assignments"
    )

    class Meta:
        unique_together = (
            "teacher",
            "student_class",
            "subject"
        )

    def __str__(self):
        return f"{self.teacher} - {self.subject} - {self.student_class}"


class Timetable(models.Model):
    class DayOfWeek(models.TextChoices):
        MONDAY = "MONDAY", "Monday"
        TUESDAY = "TUESDAY", "Tuesday"
        WEDNESDAY = "WEDNESDAY", "Wednesday"
        THURSDAY = "THURSDAY", "Thursday"
        FRIDAY = "FRIDAY", "Friday"
        SATURDAY = "SATURDAY", "Saturday"

    student_class = models.ForeignKey(
        Class, on_delete=models.CASCADE, related_name="timetable_entries"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="timetable_entries"
    )
    teacher = models.ForeignKey(
        "accounts.TeacherProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_entries",
    )
    day_of_week = models.CharField(max_length=9, choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room_number = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ("day_of_week", "start_time", "student_class__name")

    def __str__(self):
        return (
            f"Class {self.student_class} | {self.subject.name} | "
            f"{self.get_day_of_week_display()[:3]} "
            f"{self.start_time:%H:%M} - {self.end_time:%H:%M}"
        )


class Notice(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()

    teacher = models.ForeignKey(
        "accounts.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="notices"
    )

    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="notices"
    )

    attachment = models.FileField(
        upload_to="notices/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        LATE = "LATE", "Late"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="attendance_records"
    )

    student_class = models.ForeignKey(
        Class,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_records",
    )

    date = models.DateField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ABSENT,
    )

    remarks = models.TextField(blank=True)

    # Kept for compatibility with existing reports and integrations.
    is_present = models.BooleanField(default=False)

    marked_by = models.ForeignKey(
        "accounts.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="marked_attendance"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            "student",
            "date"
        )

    def __str__(self):
        return f"{self.student} - {self.date} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        self.is_present = self.status == self.Status.PRESENT
        super().save(*args, **kwargs)


class Resource(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    teacher = models.ForeignKey(
        "accounts.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="resources"
    )

    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="resources"
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="resources"
    )

    file = models.FileField(upload_to="resources/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Assessment(models.Model):

    class AssessmentType(models.TextChoices):
        TEST = "TEST", "Test"
        ASSIGNMENT = "ASSIGNMENT", "Assignment"

    class TimingMode(models.TextChoices):
        NONE = "NONE", "No Time Limit"
        ENTIRE_TEST = "ENTIRE_TEST", "Entire Test"
        PER_QUESTION = "PER_QUESTION", "Per Question"

    title = models.CharField(max_length=200)

    description = models.TextField(blank=True)

    teacher = models.ForeignKey(
        "accounts.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="assessments"
    )

    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="assessments"
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="assessments"
    )

    assessment_type = models.CharField(
        max_length=20,
        choices=AssessmentType.choices
    )

    total_marks = models.PositiveIntegerField()

    is_published = models.BooleanField(default=False)

    max_attempts = models.PositiveIntegerField(default=1)
    shuffle_questions = models.BooleanField(default=False)
    show_results_immediately = models.BooleanField(default=True)
    results_released = models.BooleanField(default=False)
    passmark_percentage = models.FloatField(default=40.0)
    access_code = models.CharField(max_length=20, blank=True, null=True)
    instructions = models.TextField(blank=True)

    # Test timing configuration

    timing_mode = models.CharField(
        max_length=20,
        choices=TimingMode.choices,
        default=TimingMode.NONE
    )

    duration_hours = models.PositiveIntegerField(
        default=0
    )

    duration_minutes = models.PositiveIntegerField(
        default=0
    )

    available_from = models.DateTimeField(
        null=True,
        blank=True
    )

    due_date = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.title} - {self.get_assessment_type_display()}"


class DoubtThread(models.Model):
    class Category(models.TextChoices):
        SYLLABUS_TOPIC = "SYLLABUS_TOPIC", "Syllabus / Topic"
        ASSIGNMENT_HOMEWORK = "ASSIGNMENT_HOMEWORK", "Assignment / Homework"
        NOTICE_ANNOUNCEMENT = "NOTICE_ANNOUNCEMENT", "Notice / Announcement"
        STUDY_RESOURCE = "STUDY_RESOURCE", "Study Resource"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        RESOLVED = "RESOLVED", "Resolved"

    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(
        max_length=24,
        choices=Category.choices,
        default=Category.SYLLABUS_TOPIC,
    )
    is_public = models.BooleanField(default=False)
    document_link = models.URLField(blank=True)
    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="doubt_threads",
    )
    student_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="doubt_threads",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="doubt_threads",
    )
    status = models.CharField(
        max_length=11,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return self.title


class DoubtAttachment(models.Model):
    thread = models.ForeignKey(
        DoubtThread,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    reply = models.ForeignKey(
        "DoubtReply",
        on_delete=models.CASCADE,
        related_name="attachments",
        null=True,
        blank=True,
    )
    file = models.FileField(
        upload_to="doubt_attachments/%Y/%m/",
        storage=PrivateDoubtAttachmentStorage(),
        blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "pdf"])],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return self.file.name.rsplit("/", 1)[-1]


class DoubtReply(models.Model):
    thread = models.ForeignKey(
        DoubtThread,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="doubt_replies",
    )
    content = models.TextField()
    is_teacher_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"Reply by {self.user} on {self.thread}"


class LeaveApplication(models.Model):
    class LeaveType(models.TextChoices):
        SICK = "SICK", "Sick Leave"
        PERSONAL = "PERSONAL", "Casual / Personal Leave"
        EMERGENCY = "EMERGENCY", "Emergency"
        OFFICIAL = "OFFICIAL", "Official / Extracurricular Event"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="leave_applications"
    )
    student_class = models.ForeignKey(
        Class, on_delete=models.SET_NULL, null=True, related_name="leave_applications"
    )
    leave_type = models.CharField(max_length=12, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    parent_acknowledgement = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewer = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_leave_applications"
    )
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "start_date", "end_date"),
                condition=models.Q(status__in=("PENDING", "APPROVED")),
                name="unique_active_student_leave_range",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="leave_end_on_or_after_start",
            ),
        ]

    @property
    def total_days(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.student} — {self.start_date} to {self.end_date}"


class LeaveAttachment(models.Model):
    application = models.ForeignKey(
        LeaveApplication, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(
        upload_to="leave_attachments/%Y/%m/",
        storage=PrivateDoubtAttachmentStorage(),
        validators=[FileExtensionValidator(["pdf", "png", "jpg", "jpeg"])],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
