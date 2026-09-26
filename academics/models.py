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

    def __str__(self):
        return f"{self.teacher} - {self.student_class} - {self.subject}"

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
        unique_together = ("teacher", "student_class", "subject")

    def __str__(self):
        return f"{self.teacher} - {self.subject} - {self.student_class}"

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
        unique_together = ("student", "date")

    def __str__(self):
        status = "Present" if self.is_present else "Absent"
        return f"{self.student} - {self.date} - {status}"


