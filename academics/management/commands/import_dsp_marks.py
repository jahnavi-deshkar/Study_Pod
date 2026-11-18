from datetime import date, datetime, time
from pathlib import Path
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Min
from django.utils import timezone

from accounts.models import StudentProfile, TeacherProfile
from academics.models import Assessment, Attendance, Class, Subject
from academics.utils.dsp_normalizer import normalize_batch, normalize_roll, parse_score
from exam_engine.models import AssessmentAttempt, Question, StudentAnswer


ROSTER_FILE = "Student_Register_And_Rough_Test_Schedule.xlsx"
MARKS_FILES = (
    "Morning_Batch_11th_Tests_Rough.xlsx",
    "Evening_11th_Marks_Sheet_Final(1).xlsx",
    "12th_Part1_Maths_Both_Batches_Mixed.xlsx",
    "Calculus_And_Prob_Tests_Dec2025.xlsx",
    "Prelims_And_MHTCET_Grand_Mocks_2026.xlsx",
)


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        raw = str(value).strip()
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
    return None


def _daytime(value):
    return timezone.make_aware(datetime.combine(value, time.min))


def _rows(sheet, header_index):
    values = list(sheet.iter_rows(values_only=True))
    if len(values) <= header_index:
        return []
    headers = values[header_index]
    return [dict(zip(headers, row)) for row in values[header_index + 1:]
            if any(cell is not None for cell in row)]


def _get(row, *names):
    mapped = {_key(key): value for key, value in row.items() if key is not None}
    for name in names:
        if _key(name) in mapped:
            return mapped[_key(name)]
    return None


def _test_code(header):
    match = re.match(r"\s*(T\d+)", str(header or ""), re.IGNORECASE)
    if match:
        number = int(match.group(1)[1:])
        return f"T{number:02d}"
    match = re.search(r"\(\s*T(\d+)\b", str(header or ""), re.IGNORECASE)
    if match:
        return f"T{int(match.group(1)):02d}"
    match = re.match(r"\s*Test[_ ]?(\d+)\b", str(header or ""), re.IGNORECASE)
    return f"T{int(match.group(1)):02d}" if match else None


class Command(BaseCommand):
    help = "Import DSP assessment metadata, marks, and test attendance."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default="raw_data")

    @transaction.atomic
    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"])
        missing = [name for name in (ROSTER_FILE, *MARKS_FILES) if not (data_dir / name).is_file()]
        if missing:
            raise CommandError("Missing required workbook(s): " + ", ".join(missing))
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise CommandError("Install openpyxl to import DSP workbooks.") from exc

        User = get_user_model()
        try:
            teacher = TeacherProfile.objects.get(user__username="teacher1")
            classes = {
                "Morning Batch": Class.objects.get(section="M", name="11"),
                "Evening Batch": Class.objects.get(section="E", name="11"),
            }
        except (TeacherProfile.DoesNotExist, Class.DoesNotExist) as exc:
            raise CommandError("Run import_dsp_roster successfully before importing marks.") from exc
        students = {normalize_roll(s.roll_number): s for s in StudentProfile.objects.select_related("user", "student_class")}
        roster_path = data_dir / ROSTER_FILE
        roster_book = load_workbook(roster_path, read_only=True, data_only=True)
        topic_sheet = roster_book["Test_Topics_Rough_List"]
        topic_rows = _rows(topic_sheet, 0)
        metadata = {}
        for row in topic_rows:
            raw_code = _get(row, "Test_Code", "Test ID", "Code", "Test_No")
            match = re.search(r"T\s*0*(\d+)", str(raw_code or ""), re.I)
            if not match:
                continue
            code = f"T{int(match.group(1)):02d}"
            metadata[code] = {
                "topic": _get(row, "Topic", "Syllabus Covered", "Topic / Syllabus Covered") or code,
                "board": _get(row, "Board_Or_CET", "Board Or CET") or "",
                "date": _date_value(_get(row, "Date_Conducted", "Date Conducted")),
                "notes": _get(row, "Paper_Setter_Notes") or "",
            }
        roster_book.close()
        if not metadata:
            raise CommandError("No T01–T30 test metadata found in Test_Topics_Rough_List.")

        assessments = {}
        for code, info in metadata.items():
            subject = self._subject(info["topic"], info["notes"])
            for batch_name, student_class in classes.items():
                assessment, _ = Assessment.objects.update_or_create(
                    title=f"{code}: {info['topic']}", student_class=student_class,
                    defaults={
                        "teacher": teacher, "subject": subject,
                        "description": f"{info['board']} {info['notes']}".strip(),
                        "assessment_type": Assessment.AssessmentType.TEST,
                        "total_marks": 100, "is_published": True,
                        "workflow_status": Assessment.WorkflowStatus.PUBLISHED,
                        "show_results_immediately": True,
                        "results_released": True,
                    },
                )
                assessments[(batch_name, code)] = assessment

        # Remove only our synthetic score questions/attempts before rebuilding.
        imported_questions = Question.objects.filter(
            assessment__in=assessments.values(),
            question_text="Imported spreadsheet score",
        )
        imported_started = imported_questions.aggregate(first=Min("created_at"))["first"]
        if imported_questions.exists():
            attempt_ids = StudentAnswer.objects.filter(
                question__in=imported_questions
            ).values_list("attempt_id", flat=True)
            AssessmentAttempt.objects.filter(pk__in=attempt_ids).delete()
            imported_questions.delete()
        roll_numbers = list(students)
        if imported_started:
            # Older importer revisions did not tag their attendance rows. This
            # one-time cleanup boundary is the creation time of our score marker.
            Attendance.objects.filter(
                marked_by=teacher,
                student__roll_number__in=roll_numbers,
                created_at__gte=imported_started,
                remarks="",
            ).delete()
        Attendance.objects.filter(
            marked_by=teacher,
            student__roll_number__in=roll_numbers,
            remarks="DSP marks import",
        ).delete()

        marks = self._collect_marks(data_dir, load_workbook)
        # Snapshot counters report final database state for this import scope.
        written = 0
        absent = 0
        for roll, code, raw_score in marks:
            roll = normalize_roll(roll)
            student = students.get(roll)
            info = metadata.get(code)
            if student is None or info is None or info["date"] is None:
                continue
            batch_name = normalize_batch(student.batch) or self._batch_from_roll(roll)
            assessment = assessments.get((batch_name, code))
            if assessment is None:
                continue
            score, attendance_status = parse_score(raw_score)
            Attendance.objects.update_or_create(
                student=student, date=info["date"],
                defaults={"student_class": student.student_class,
                          "status": attendance_status, "marked_by": teacher,
                          "remarks": "DSP marks import"},
            )
            if attendance_status == Attendance.Status.ABSENT:
                absent += 1
                continue
            attempt_time = _daytime(info["date"])
            attempt = (AssessmentAttempt.objects.filter(assessment=assessment, student=student)
                       .order_by("-pk").first())
            if attempt is None:
                attempt = AssessmentAttempt.objects.create(
                    assessment=assessment, student=student, started_at=attempt_time,
                    submitted_at=attempt_time, status=AssessmentAttempt.Status.EVALUATED,
                )
            else:
                attempt.started_at = attempt_time
                attempt.submitted_at = attempt_time
                attempt.status = AssessmentAttempt.Status.EVALUATED
                attempt.save(update_fields=["started_at", "submitted_at", "status"])
            question, _ = Question.objects.get_or_create(
                assessment=assessment, question_text="Imported spreadsheet score",
                defaults={"question_type": Question.QuestionType.SHORT_ANSWER,
                          "marks": 100, "order": 9999},
            )
            answer, _ = StudentAnswer.objects.update_or_create(
                attempt=attempt, question=question,
                defaults={"answer_text": str(raw_score), "awarded_marks": score},
            )
            StudentAnswer.objects.filter(pk=answer.pk).update(answered_at=attempt_time)
            written += 1

        total_assessments = Assessment.objects.filter(title__regex=r"^T\d{2}:").count()
        evaluated = AssessmentAttempt.objects.filter(status=AssessmentAttempt.Status.EVALUATED,
                                                       assessment__title__regex=r"^T\d{2}:").count()
        attendance_count = Attendance.objects.filter(marked_by=teacher).count()
        self.stdout.write(self.style.SUCCESS(
            f"DSP marks import complete: {total_assessments} assessments, {evaluated} evaluated attempts, "
            f"{attendance_count} attendance records; processed {written} present scores and {absent} absences."
        ))

    @staticmethod
    def _batch_from_roll(roll):
        return "Morning Batch" if roll.startswith("M") else "Evening Batch" if roll.startswith("E") else ""

    @staticmethod
    def _subject(topic, notes):
        text = f"{topic} {notes}".casefold()
        if any(word in text for word in ("prob", "statistics", "distribution")):
            code = "DSP-PROB"
        elif any(word in text for word in ("mock", "prelim", "cet", "full syllabus", "grand")):
            code = "DSP-MOCK"
        elif any(word in text for word in ("calculus", "differentiation", "integration", "aod", "d.e.")):
            code = "DSP-CALC"
        elif any(word in text for word in ("vector", "3d")):
            code = "DSP-VECT"
        elif any(word in text for word in ("trig", "angle", "geometry", "coordinate")):
            code = "DSP-TRIG"
        else:
            code = "DSP-ALG"
        return Subject.objects.get(code=code)

    def _collect_marks(self, data_dir, load_workbook):
        records = []

        def matrix(filename, sheet_name, header_row, batch, code_mode="headers", fixed=None):
            book = load_workbook(data_dir / filename, read_only=True, data_only=True)
            if sheet_name not in book.sheetnames:
                raise CommandError(f"Sheet {sheet_name!r} missing from {filename}")
            sheet = book[sheet_name]
            values = list(sheet.iter_rows(values_only=True))
            if sheet_name == "Aug_Tests_Sheet2":
                # The supplied workbook has row-zero headers; some exports have
                # two leading banner rows, so accept either layout.
                for candidate in range(min(3, len(values))):
                    cells = values[candidate]
                    if any(_test_code(h) for h in cells) and any(_key(h) == "id" for h in cells):
                        header_row = candidate
                        break
            headers = values[header_row] if len(values) > header_row else ()
            ordered_codes = {}
            if code_mode == "ordered":
                score_columns = [i for i, header in enumerate(headers)
                                 if re.match(r"^\s*\d{1,2}/\d{1,2}\b", str(header or ""))]
                ordered_codes = {column: f"T{i + 1:02d}" for i, column in enumerate(score_columns)}
            for row in [dict(zip(headers, values)) for values in values[header_row + 1:]
                        if any(cell is not None for cell in values)]:
                roll = _get(row, "Roll", "Roll_No", "Roll_ID", "Student_Roll", "Roll Number", "RollNo", "ID")
                if not roll:
                    continue
                for index, (header, raw) in enumerate(row.items()):
                    code = (fixed.get(index) if fixed else ordered_codes.get(index)
                            if code_mode == "ordered" else _test_code(header))
                    if fixed and code is None:
                        continue
                    if code:
                        records.append((roll, code, raw))
            book.close()

        matrix(MARKS_FILES[0], "Morn_11th_Marks", 2, "Morning Batch")
        matrix(MARKS_FILES[1], "June_July_Tests", 0, "Evening Batch", "ordered")
        matrix(MARKS_FILES[1], "Aug_Tests_Sheet2", 2, "Evening Batch")
        matrix(MARKS_FILES[2], "Sheet1 (Part 1 Dump)", 3, "", "headers")
        matrix(MARKS_FILES[3], "Diff_And_AOD", 1, "", "headers")
        matrix(MARKS_FILES[3], "Integration_DE_Combo", 0, "", "headers")
        matrix(MARKS_FILES[3], "Prob_Dist_T26", 1, "", "headers")
        matrix(MARKS_FILES[4], "HSC_Prelims_P1_P2", 0, "", "headers")

        book = load_workbook(data_dir / MARKS_FILES[4], read_only=True, data_only=True)
        for row in _rows(book["CET_Mocks_Stacked_Log"], 0):
            roll = _get(row, "Student_Roll", "Roll", "Roll_No")
            code = _test_code(_get(row, "Exam_Code"))
            raw = _get(row, "Score_Obtained")
            if roll and code in {"T29", "T30"}:
                records.append((roll, code, raw))
        book.close()
        return records
