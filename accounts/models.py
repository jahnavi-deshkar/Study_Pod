from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):

    class Role(models.TextChoices):
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"
        PARENT = "PARENT", "Parent"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
    )

    def __str__(self):
        return self.username


class TeacherProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile"
    )
    employee_id = models.CharField(max_length=50, unique=True)
    department = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class StudentProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile"
    )
    roll_number = models.CharField(max_length=50, unique=True)
    student_class = models.ForeignKey(
        "academics.Class",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students"
    )
    parent = models.ForeignKey(
        "ParentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students"
    )

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class ParentProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="parent_profile"
    )
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username



