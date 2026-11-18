from pathlib import Path
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ParentProfile, StudentProfile, TeacherProfile
from academics.models import Class, Subject, TeachingAssignment, Timetable
from academics.utils.dsp_normalizer import normalize_batch, normalize_name, normalize_roll


WORKBOOK = "Student_Register_And_Rough_Test_Schedule.xlsx"
SUBJECTS = (
    ("Algebra & Logic", "DSP-ALG"),
    ("Trigonometry & 2D Geometry", "DSP-TRIG"),
    ("Vectors & 3D Geometry", "DSP-VECT"),
    ("Calculus", "DSP-CALC"),
    ("Probability & Statistics", "DSP-PROB"),
    ("Full Syllabus Maths Mocks", "DSP-MOCK"),
)
DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY")


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _field(row, *names):
    normalized = {_key(key): value for key, value in row.items() if key is not None}
    for name in names:
        if _key(name) in normalized:
            return normalized[_key(name)]
    return None


class Command(BaseCommand):
    help = "Import the DSP student roster, parent demos, subjects, and timetable."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default="raw_data")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["data_dir"]) / WORKBOOK
        if not path.is_file():
            raise CommandError(f"Roster workbook not found: {path}")
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise CommandError("Install openpyxl to import the roster.") from exc
        workbook = load_workbook(path, read_only=True, data_only=True)
        if not {"Student_Admission_List", "Test_Topics_Rough_List"}.issubset(workbook.sheetnames):
            raise CommandError("Workbook must contain Student_Admission_List and Test_Topics_Rough_List sheets.")
        students_rows = list(self._rows(workbook["Student_Admission_List"]))
        topic_rows = list(self._rows(workbook["Test_Topics_Rough_List"]))

        # Read the syllabus sheet too, so a malformed or empty source cannot silently seed a roster.
        if not topic_rows:
            raise CommandError("Test_Topics_Rough_List contains no topic rows.")
        batches = {}
        for batch_name, section in (("Morning Batch", "M"), ("Evening Batch", "E")):
            batches[batch_name], _ = Class.objects.get_or_create(
                name="11", section=section, academic_year="2025-26"
            )
        subjects = [Subject.objects.get_or_create(code=code, defaults={"name": name})[0]
                    for name, code in SUBJECTS]
        User = get_user_model()
        teacher_user, created = User.objects.get_or_create(
            username="teacher1",
            defaults={"first_name": "D.S.P.", "last_name": "Sir", "role": User.Role.TEACHER},
        )
        if created:
            teacher_user.set_password("password123")
            teacher_user.save()
        teacher_user.role = User.Role.TEACHER
        teacher_user.first_name, teacher_user.last_name = "D.S.P.", "Sir"
        teacher_user.save(update_fields=["role", "first_name", "last_name"])
        teacher, _ = TeacherProfile.objects.get_or_create(
            user=teacher_user, defaults={"employee_id": "DSP-TEACHER-1", "department": "Mathematics"}
        )
        for student_class in batches.values():
            for subject in subjects:
                TeachingAssignment.objects.get_or_create(
                    teacher=teacher, student_class=student_class, subject=subject
                )

        imported = 0
        for row in students_rows:
            roll = normalize_roll(_field(row, "Roll", "Roll_No", "Roll Number", "Roll_Code"))
            name = normalize_name(_field(row, "Full_Name", "Full Name", "Name"))
            if not roll or not name:
                continue
            batch_name = "Morning Batch" if roll.startswith("M") else "Evening Batch" if roll.startswith("E") else ""
            if not batch_name:
                continue
            pieces = name.split()
            username = roll.lower()
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": pieces[0], "last_name": " ".join(pieces[1:]), "role": User.Role.STUDENT},
            )
            if created:
                user.set_password("student123")
            user.first_name, user.last_name, user.role = pieces[0], " ".join(pieces[1:]), User.Role.STUDENT
            user.save()
            StudentProfile.objects.update_or_create(
                user=user,
                defaults={"roll_number": roll, "batch": batch_name, "student_class": batches[batch_name]},
            )
            imported += 1

        self._parent(User, "parent1", "Rajesh", "Sathe", ["M1", "M8"])
        self._parent(User, "parent_e49", "Suresh", "Agarkar", ["E49"])

        timetable_count = 0
        for student_class, (start, end) in zip(batches.values(), (("07:30", "09:30"), ("17:30", "19:30"))):
            for day, subject in zip(DAYS, subjects):
                _, created = Timetable.objects.get_or_create(
                    student_class=student_class, subject=subject, teacher=teacher,
                    day_of_week=day, start_time=start,
                    defaults={"end_time": end, "room_number": "DSP Classroom"},
                )
                timetable_count += int(created)
        self.stdout.write(self.style.SUCCESS(
            f"DSP roster ready: 2 batches, 6 subjects, {imported} students, 2 parents, "
            f"{timetable_count} timetable entries created."
        ))

    @staticmethod
    def _rows(sheet):
        iterator = sheet.iter_rows(values_only=True)
        headers = next(iterator, ())
        return [dict(zip(headers, values)) for values in iterator if any(v is not None for v in values)]

    @staticmethod
    def _parent(User, username, first_name, last_name, rolls):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first_name, "last_name": last_name, "role": User.Role.PARENT},
        )
        if created:
            user.set_password("password123")
        user.first_name, user.last_name, user.role = first_name, last_name, User.Role.PARENT
        user.save()
        parent, _ = ParentProfile.objects.get_or_create(user=user)
        StudentProfile.objects.filter(roll_number__in=rolls).update(parent=parent)
