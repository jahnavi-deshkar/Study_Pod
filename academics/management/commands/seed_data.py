from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import ParentProfile, StudentProfile, TeacherProfile
from academics.models import Assessment, Class, Subject, TeachingAssignment, Timetable


class Command(BaseCommand):
    help = "Create or refresh the StudyPod local demonstration accounts and records."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        student_class, _ = Class.objects.get_or_create(
            name="10", section="A", academic_year="2026-27"
        )
        math, _ = Subject.objects.get_or_create(
            code="SEED-MATH", defaults={"name": "Mathematics"}
        )
        science, _ = Subject.objects.get_or_create(
            code="SEED-SCI", defaults={"name": "Science"}
        )

        teacher_user = self._user(User, "teacher1", "Teacher", "One", User.Role.TEACHER)
        teacher, _ = TeacherProfile.objects.get_or_create(
            user=teacher_user,
            defaults={"employee_id": "SEED-T-001", "department": "Science and Mathematics"},
        )
        teacher.department = "Science and Mathematics"
        teacher.save(update_fields=["department"])

        demo_students = []
        for username, first_name, roll_number in (
            ("student1", "Student", "SEED-S-001"),
            ("student2", "Student", "SEED-S-002"),
        ):
            user = self._user(User, username, first_name, username[-1], User.Role.STUDENT)
            profile, _ = StudentProfile.objects.get_or_create(
                user=user,
                defaults={"roll_number": roll_number, "student_class": student_class},
            )
            profile.student_class = student_class
            profile.save(update_fields=["student_class"])
            demo_students.append(profile)

        parent_user = self._user(User, "parent1", "Parent", "One", User.Role.PARENT)
        parent, _ = ParentProfile.objects.get_or_create(user=parent_user)
        demo_students[0].parent = parent
        demo_students[0].save(update_fields=["parent"])

        for subject in (math, science):
            TeachingAssignment.objects.get_or_create(
                teacher=teacher,
                student_class=student_class,
                subject=subject,
            )

        for day, subject, start, end, room in (
            (Timetable.DayOfWeek.MONDAY, math, "09:00", "09:50", "101"),
            (Timetable.DayOfWeek.WEDNESDAY, science, "10:00", "10:50", "Lab 1"),
        ):
            Timetable.objects.get_or_create(
                student_class=student_class,
                subject=subject,
                teacher=teacher,
                day_of_week=day,
                start_time=start,
                defaults={"end_time": end, "room_number": room},
            )

        assessment, _ = Assessment.objects.get_or_create(
            title="Sample Mathematics Assessment",
            teacher=teacher,
            student_class=student_class,
            subject=math,
            defaults={
                "description": "A sample assessment for local development.",
                "assessment_type": Assessment.AssessmentType.TEST,
                "total_marks": 10,
                "is_published": False,
                "instructions": "Add questions and publish this assessment when ready.",
            },
        )

        self.stdout.write(self.style.SUCCESS(
            "StudyPod demo data is ready: teacher1, student1, student2, parent1 (password: password123)."
        ))
        self.stdout.write(f"Class: {student_class}; subjects: {math.name}, {science.name}.")
        self.stdout.write(f"Sample assessment: {assessment.title} (draft).")

    @staticmethod
    def _user(User, username, first_name, last_name, role):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "role": role,
            },
        )
        user.first_name = first_name
        user.last_name = last_name
        user.role = role
        user.is_active = True
        user.set_password("password123")
        user.save()
        return user
