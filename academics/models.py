from django.db import models


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
    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="attendance_records"
    )

    date = models.DateField()
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
        status = "Present" if self.is_present else "Absent"
        return f"{self.student} - {self.date} - {status}"


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