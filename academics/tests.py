from io import StringIO
from io import BytesIO
from datetime import date
import importlib.util
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
import zipfile
from django.core.files.uploadedfile import SimpleUploadedFile

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ParentProfile, StudentProfile, TeacherProfile, User
from exam_engine.models import AssessmentAttempt, Question, StudentAnswer

from .models import Assessment, Attendance, Class, DoubtAttachment, DoubtReply, DoubtThread, Notice, Resource, Subject, TeachingAssignment, Timetable
from .utils.dsp_normalizer import normalize_batch, normalize_name, normalize_roll, parse_score


class DSPRosterImportTests(TestCase):
    def test_normalizers(self):
        self.assertEqual(normalize_roll(" m-3 "), "M3")
        self.assertEqual(normalize_roll("e-75"), "E75")
        self.assertEqual(normalize_batch("Morn"), "Morning Batch")
        self.assertEqual(normalize_batch("eve"), "Evening Batch")
        self.assertEqual(normalize_name("Agarkar, Aditi"), "Aditi Agarkar")
        self.assertEqual(normalize_name("TEJASWINI SOMAN"), "Tejaswini Soman")

    @skipUnless(
        importlib.util.find_spec("openpyxl"), "openpyxl is required for XLSX import tests"
    )
    def test_import_is_idempotent_and_links_demo_parents(self):
        from openpyxl import Workbook

        with TemporaryDirectory() as directory:
            path = Path(directory) / "Student_Register_And_Rough_Test_Schedule.xlsx"
            workbook = Workbook()
            roster = workbook.active
            roster.title = "Student_Admission_List"
            roster.append(["Roll", "Full_Name"])
            roster.append(["M1", "Sathe, Shruti"])
            roster.append(["M8", "Sathe, Gaurav"])
            roster.append(["E49", "Agarkar, Aditi"])
            topics = workbook.create_sheet("Test_Topics_Rough_List")
            topics.append(["Test_ID", "Topic"])
            topics.append(["T01", "Algebra"])
            workbook.save(path)

            call_command("import_dsp_roster", data_dir=directory, stdout=StringIO())
            call_command("import_dsp_roster", data_dir=directory, stdout=StringIO())

        self.assertEqual(Class.objects.filter(section__in=("M", "E")).count(), 2)
        self.assertEqual(Subject.objects.filter(code__startswith="DSP-").count(), 6)
        self.assertEqual(StudentProfile.objects.filter(roll_number__in=("M1", "M8", "E49")).count(), 3)
        self.assertEqual(User.objects.filter(username__in=("parent1", "parent_e49")).count(), 2)
        self.assertEqual(StudentProfile.objects.get(roll_number="M1").parent.user.username, "parent1")
        self.assertEqual(StudentProfile.objects.get(roll_number="E49").parent.user.username, "parent_e49")
        self.assertEqual(Timetable.objects.filter(student_class__section__in=("M", "E")).count(), 12)

    @skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl is required for XLSX import tests")
    def test_roster_is_extracted_from_xlsx_named_archive(self):
        from openpyxl import Workbook

        with TemporaryDirectory() as directory:
            payload = BytesIO()
            workbook = Workbook()
            roster = workbook.active
            roster.title = "Student_Admission_List"
            roster.append(["Roll_Code", "Full_Name"])
            roster.append(["M1", "Sathe, Shruti"])
            topics = workbook.create_sheet("Test_Topics_Rough_List")
            topics.append(["Code", "Topic"])
            topics.append(["T01", "Algebra"])
            workbook.save(payload)
            archive_path = Path(directory) / "DSP’s Mathematics AcademyCoachingDataSet.xlsx"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("workbooks/Student_Register_And_Rough_Test_Schedule.xlsx", payload.getvalue())

            call_command("import_dsp_roster", data_dir=directory, stdout=StringIO())

            self.assertTrue((Path(directory) / "Student_Register_And_Rough_Test_Schedule.xlsx").exists())
            self.assertTrue(StudentProfile.objects.filter(roll_number="M1").exists())


class DSPMarksImportTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="teacher1", password="pw", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, employee_id="DSP-MARKS-T")
        self.morning = Class.objects.create(name="11", section="M", academic_year="2025-26")
        Class.objects.create(name="11", section="E", academic_year="2025-26")
        for name, code in (
            ("Algebra & Logic", "DSP-ALG"), ("Trigonometry & 2D Geometry", "DSP-TRIG"),
            ("Vectors & 3D Geometry", "DSP-VECT"), ("Calculus", "DSP-CALC"),
            ("Probability & Statistics", "DSP-PROB"), ("Full Syllabus Maths Mocks", "DSP-MOCK"),
        ):
            Subject.objects.create(name=name, code=code)
        self.student_user = User.objects.create_user(
            username="m1", password="pw", role=User.Role.STUDENT
        )
        StudentProfile.objects.create(
            user=self.student_user, roll_number="M1", batch="Morning Batch", student_class=self.morning
        )

    def test_parse_score_and_absence_values(self):
        self.assertEqual(parse_score("94/100"), (94.0, "PRESENT"))
        self.assertEqual(parse_score("68/100"), (68.0, "PRESENT"))
        self.assertEqual(parse_score("AB"), (None, "ABSENT"))
        self.assertEqual(parse_score("Absent"), (None, "ABSENT"))
        self.assertEqual(parse_score("-"), (None, "ABSENT"))
        self.assertEqual(parse_score(None), (None, "ABSENT"))

    @skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl is required for XLSX import tests")
    def test_marks_import_is_idempotent(self):
        from openpyxl import Workbook

        filenames = (
            "Morning_Batch_11th_Tests_Rough.xlsx",
            "Evening_11th_Marks_Sheet_Final(1).xlsx",
            "12th_Part1_Maths_Both_Batches_Mixed.xlsx",
            "Calculus_And_Prob_Tests_Dec2025.xlsx",
            "Prelims_And_MHTCET_Grand_Mocks_2026.xlsx",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            book = Workbook()
            ws = book.active
            ws.title = "Student_Admission_List"
            ws.append(["Roll", "Full_Name"])
            topics = book.create_sheet("Test_Topics_Rough_List")
            topics.append(["Test_Code", "Topic", "Board_Or_CET", "Date_Conducted", "Max_Marks", "Paper_Setter_Notes"])
            topics.append(["T01", "Algebra and Logic", "Board", date(2025, 6, 15), 100, "Algebra"])
            book.save(root / "Student_Register_And_Rough_Test_Schedule.xlsx")

            for filename in filenames:
                wb = Workbook()
                if filename == filenames[0]:
                    sheet = wb.active
                    sheet.title = "Morn_11th_Marks"
                    sheet.append(["Roster"])
                    sheet.append(["Marks"])
                    sheet.append(["Roll_No", "Student Full Name", "Batch_Shift", "T1_Algebra"])
                    sheet.append(["M1", "Student One", "Morning", 94])
                elif filename == filenames[1]:
                    sheet = wb.active
                    sheet.title = "June_July_Tests"
                    sheet.append(["Roll_No", "Student Full Name", "Batch_Shift", "15/06 Angle & Trig-I"])
                    sheet.append(["E1", "Evening One", "Evening", 94])
                    second = wb.create_sheet("Aug_Tests_Sheet2")
                    second.append(["Cover"])
                    second.append(["Cover"])
                    second.append(["Roll_No", "Student Full Name", "Test_7"])
                elif filename == filenames[2]:
                    sheet = wb.active
                    sheet.title = "Sheet1 (Part 1 Dump)"
                    for _ in range(3):
                        sheet.append(["Cover"])
                    sheet.append(["Sr", "Batch_Name", "Roll", "Full_Name", "M/F", "T11 Algebra"])
                elif filename == filenames[3]:
                    sheet = wb.active
                    sheet.title = "Diff_And_AOD"
                    sheet.append(["Cover"])
                    sheet.append(["Roll_No", "T20 Differential"])
                    wb.create_sheet("Integration_DE_Combo").append(["Roll_No", "T22 Integration"])
                    other = wb.create_sheet("Prob_Dist_T26")
                    other.append(["Cover"])
                    other.append(["Roll_No", "Marks_Out_Of_100 (T26 Probability)"])
                else:
                    sheet = wb.active
                    sheet.title = "HSC_Prelims_P1_P2"
                    sheet.append(["Roll_No", "T27 Prelim"])
                    wb.create_sheet("CET_Mocks_Stacked_Log").append(["Exam_Code", "Student_Roll", "Score_Obtained"])
                wb.save(root / filename)

            call_command("import_dsp_marks", data_dir=directory, stdout=StringIO())
            call_command("import_dsp_marks", data_dir=directory, stdout=StringIO())

        self.assertEqual(Assessment.objects.filter(title__startswith="T01:").count(), 2)
        attempts = AssessmentAttempt.objects.filter(student__roll_number="M1", status="EVALUATED")
        self.assertEqual(attempts.count(), 1)
        self.assertEqual(float(attempts.first().score), 94.0)
        attendance = Attendance.objects.get(student__roll_number="M1")
        self.assertEqual(attendance.status, Attendance.Status.PRESENT)


class DSPCommunityImportTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="teacher1", password="pw", role=User.Role.TEACHER,
            first_name="D.S.P.", last_name="Sir",
        )
        TeacherProfile.objects.create(user=self.teacher_user, employee_id="DSP-COMMUNITY-T")
        classes = {
            "M": Class.objects.create(name="11", section="M", academic_year="2025-26"),
            "E": Class.objects.create(name="11", section="E", academic_year="2025-26"),
        }
        self.subjects = [
            Subject.objects.create(name=name, code=code)
            for name, code in (
                ("Algebra & Logic", "DSP-ALG"),
                ("Trigonometry & 2D Geometry", "DSP-TRIG"),
                ("Vectors & 3D Geometry", "DSP-VECT"),
                ("Calculus", "DSP-CALC"),
                ("Probability & Statistics", "DSP-PROB"),
                ("Full Syllabus Maths Mocks", "DSP-MOCK"),
            )
        ]
        for username, name, batch in (
            ("m1", "Shruti Sathe", "M"), ("m4", "Student Four", "M"),
            ("m12", "Student Twelve", "M"), ("e49", "Aditi Agarkar", "E"),
            ("e90", "Student Ninety", "E"), ("e23", "Student Twenty Three", "E"),
        ):
            user = User.objects.create_user(
                username=username, password="pw", role=User.Role.STUDENT,
                first_name=name.split()[0], last_name=" ".join(name.split()[1:]),
            )
            StudentProfile.objects.create(
                user=user, roll_number=username.upper(), batch="Morning Batch" if batch == "M" else "Evening Batch",
                student_class=classes[batch],
            )

    def test_community_import_is_idempotent_and_writes_resource_files(self):
        with TemporaryDirectory() as media_dir:
            with override_settings(MEDIA_ROOT=media_dir):
                call_command("import_dsp_community", stdout=StringIO())
                call_command("import_dsp_community", stdout=StringIO())

                self.assertEqual(Notice.objects.count(), 8)
                self.assertEqual(Resource.objects.count(), 12)
                self.assertEqual(DoubtThread.objects.count(), 6)
                self.assertEqual(DoubtReply.objects.count(), 6)
                self.assertEqual(
                    DoubtThread.objects.filter(status=DoubtThread.Status.RESOLVED).count(), 4
                )
                self.assertEqual(
                    DoubtThread.objects.filter(status=DoubtThread.Status.OPEN).count(), 2
                )
                self.assertTrue(all(
                    (Path(media_dir) / resource.file.name).is_file()
                    for resource in Resource.objects.all()
                ))
                self.assertEqual(
                    Resource.objects.values_list("file", flat=True).distinct().count(), 6
                )


class DSPRecruiterPortalSmokeTests(TestCase):
    resource_path = "resources/Calculus_Integration_Standard_Formulae.txt"

    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="teacher1", password="password123", role=User.Role.TEACHER,
            first_name="D.S.P.", last_name="Sir",
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="DSP-SMOKE-T", department="Mathematics"
        )
        self.morning = Class.objects.create(name="11", section="M", academic_year="2025-26")
        self.evening = Class.objects.create(name="11", section="E", academic_year="2025-26")
        self.subject = Subject.objects.create(name="Calculus", code="DSP-SMOKE-CALC")
        for student_class in (self.morning, self.evening):
            TeachingAssignment.objects.create(
                teacher=self.teacher, student_class=student_class, subject=self.subject
            )
            Timetable.objects.create(
                student_class=student_class, subject=self.subject, teacher=self.teacher,
                day_of_week=Timetable.DayOfWeek.MONDAY,
                start_time="07:30" if student_class == self.morning else "17:30",
                end_time="09:30" if student_class == self.morning else "19:30",
            )
            Notice.objects.create(
                teacher=self.teacher, student_class=student_class,
                title=f"{student_class.section} batch weekly update", content="Check the current test schedule.",
            )

        self.parent_user = User.objects.create_user(
            username="parent1", password="password123", role=User.Role.PARENT,
            first_name="Rajesh", last_name="Sathe",
        )
        self.parent = ParentProfile.objects.create(user=self.parent_user)
        self.other_parent_user = User.objects.create_user(
            username="parent_e49", password="password123", role=User.Role.PARENT,
            first_name="Suresh", last_name="Agarkar",
        )
        self.other_parent = ParentProfile.objects.create(user=self.other_parent_user)
        self.m1 = self._student("m1", "Shruti", "Sathe", "M1", self.morning, self.parent)
        self.m8 = self._student("m8", "Gaurav", "Sathe", "M8", self.morning, self.parent)
        self.e49 = self._student("e49", "Aditi", "Agarkar", "E49", self.evening, self.other_parent)

        self.resource = Resource.objects.create(
            title="Calculus integration formulae", description="Standard revision formulas.",
            teacher=self.teacher, student_class=self.morning, subject=self.subject,
            file=self.resource_path,
        )
        self.thread = DoubtThread.objects.create(
            title="Question about a definite integral", content="How should I choose a substitution?",
            student=self.m1, student_class=self.morning, subject=self.subject,
            is_public=True, status=DoubtThread.Status.OPEN,
        )

    @staticmethod
    def _student(username, first_name, last_name, roll, student_class, parent):
        user = User.objects.create_user(
            username=username, password="student123", role=User.Role.STUDENT,
            first_name=first_name, last_name=last_name,
        )
        return StudentProfile.objects.create(
            user=user, roll_number=roll, batch="Morning Batch" if roll.startswith("M") else "Evening Batch",
            student_class=student_class, parent=parent,
        )

    def assert_pages_ok(self, paths):
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, f"{path} returned {response.status_code}")

    def test_teacher_portal_routes_and_resource_pages_survive_vector_store_failure(self):
        self.client.force_login(self.teacher_user)
        routes = (
            reverse("dashboard"), reverse("teacher_analytics"), reverse("teacher_timetable"),
            reverse("test_management"), reverse("notices"), reverse("resource_list"),
            reverse("doubt_threads"), reverse("teacher_resource_detail", args=[self.resource.pk]),
        )
        with patch(
            "ai_suggestions.services.vector_store.StudyPodVectorStore",
            side_effect=OSError("Hugging Face is offline"),
        ):
            self.assert_pages_ok(routes)

    def test_student_portal_routes_and_resource_download(self):
        student_user = self.m1.user
        self.client.force_login(student_user)
        self.assert_pages_ok((
            reverse("dashboard"), reverse("student_analytics"), reverse("student_timetable"),
            reverse("notices"), reverse("resource_list"), reverse("doubt_threads"),
            reverse("student_resource_detail", args=[self.resource.pk]),
        ))
        with self.resource.file.open("rb") as study_file:
            self.assertIn(b"Integration by parts", study_file.read())

    def test_parent_read_only_routes_and_multi_child_selection(self):
        self.client.force_login(self.parent_user)
        self.assert_pages_ok((
            reverse("dashboard"), reverse("notices"), reverse("resource_list"),
            reverse("doubt_threads"),
        ))
        progress = self.client.get(reverse("parent_analytics"), {"student_id": self.m8.pk})
        timetable = self.client.get(reverse("parent_timetable"), {"student_id": self.m8.pk})
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(timetable.status_code, 200)
        self.assertEqual(progress.context["selected_child"].pk, self.m8.pk)
        self.assertEqual(timetable.context["selected_child"].pk, self.m8.pk)
        self.assertFalse(self.client.get(reverse("doubt_threads")).context["can_create_thread"])
        with self.resource.file.open("rb") as study_file:
            self.assertTrue(study_file.read())


class DSPDemoOrchestratorTests(TestCase):
    @patch("academics.management.commands.setup_dsp_demo.call_command")
    def test_setup_command_runs_all_stages_in_order_and_forwards_data_dir(self, mocked_call):
        output = StringIO()
        call_command("setup_dsp_demo", data_dir="fixture-workbooks", stdout=output)

        self.assertEqual(
            [call.args[0] for call in mocked_call.call_args_list],
            ["import_dsp_roster", "import_dsp_marks", "import_dsp_community"],
        )
        self.assertTrue(all(
            call.kwargs["data_dir"] == "fixture-workbooks"
            for call in mocked_call.call_args_list[:2]
        ))
        self.assertNotIn("data_dir", mocked_call.call_args_list[2].kwargs)
        self.assertIn("Stage 1/3", output.getvalue())
        self.assertIn("Stage 3/3", output.getvalue())


class AttendanceWorkflowTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="attendance-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-ACADEMIC-ATT"
        )
        self.student_class = Class.objects.create(
            name="10", section="A", academic_year="2026-27"
        )
        self.other_class = Class.objects.create(
            name="11", section="B", academic_year="2026-27"
        )
        self.subject = Subject.objects.create(name="Science", code="SCI-ATT-WORKFLOW")
        TeachingAssignment.objects.create(
            teacher=self.teacher,
            student_class=self.student_class,
            subject=self.subject,
        )
        self.student_one = self.make_student("att-student-one", "R-1")
        self.student_two = self.make_student("att-student-two", "R-2")
        self.other_student = self.make_student(
            "att-other-student", "R-3", student_class=self.other_class
        )

    def make_student(self, username, roll_number, student_class=None):
        user = User.objects.create_user(
            username=username, password="test-pass", role=User.Role.STUDENT
        )
        return StudentProfile.objects.create(
            user=user,
            roll_number=roll_number,
            student_class=student_class or self.student_class,
        )

    def test_teacher_selection_defaults_to_today_and_only_lists_assigned_classes(self):
        self.client.force_login(self.teacher_user)

        response = self.client.get(reverse("teacher_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, timezone.localdate().isoformat())
        self.assertContains(response, str(self.student_class))
        self.assertNotContains(response, str(self.other_class))

    def test_teacher_can_load_existing_records_with_status_and_notes(self):
        record = Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=date(2026, 10, 4),
            status=Attendance.Status.LATE,
            remarks="Arrived after the bell",
            marked_by=self.teacher,
        )
        self.assertFalse(record.is_present)
        self.client.force_login(self.teacher_user)

        response = self.client.post(reverse("teacher_attendance"), {
            "action": "load",
            "student_class": self.student_class.id,
            "date": "2026-10-04",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="status_%s" value="LATE" checked' % self.student_one.id)
        self.assertContains(response, "Arrived after the bell")

    def test_teacher_batch_save_creates_and_updates_roster_records(self):
        existing = Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=date(2026, 10, 4),
            status=Attendance.Status.ABSENT,
            marked_by=self.teacher,
        )
        self.client.force_login(self.teacher_user)

        response = self.client.post(reverse("teacher_attendance"), {
            "action": "save",
            "student_class": self.student_class.id,
            "date": "2026-10-04",
            f"status_{self.student_one.id}": "PRESENT",
            f"remarks_{self.student_one.id}": "",
            f"status_{self.student_two.id}": "LATE",
            f"remarks_{self.student_two.id}": "Bus delay",
        })

        self.assertRedirects(
            response,
            f"{reverse('teacher_attendance')}?student_class={self.student_class.id}&date=2026-10-04",
        )
        existing.refresh_from_db()
        self.assertEqual(existing.status, Attendance.Status.PRESENT)
        self.assertTrue(existing.is_present)
        created = Attendance.objects.get(student=self.student_two, date=date(2026, 10, 4))
        self.assertEqual(created.status, Attendance.Status.LATE)
        self.assertEqual(created.remarks, "Bus delay")
        self.assertEqual(Attendance.objects.filter(date=date(2026, 10, 4)).count(), 2)

    def test_teacher_cannot_access_or_save_unassigned_class(self):
        self.client.force_login(self.teacher_user)

        response = self.client.post(reverse("teacher_attendance"), {
            "action": "save",
            "student_class": self.other_class.id,
            "date": "2026-10-04",
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Attendance.objects.exists())

    def test_student_sees_only_own_records_and_correct_metrics(self):
        test_date = date(2026, 10, 4)
        Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=test_date,
            status=Attendance.Status.PRESENT,
            remarks="Own private note",
            marked_by=self.teacher,
        )
        Attendance.objects.create(
            student=self.student_one,
            student_class=self.student_class,
            date=date(2026, 10, 3),
            status=Attendance.Status.LATE,
            marked_by=self.teacher,
        )
        Attendance.objects.create(
            student=self.student_two,
            student_class=self.student_class,
            date=test_date,
            status=Attendance.Status.ABSENT,
            remarks="Other student's note",
            marked_by=self.teacher,
        )
        self.client.force_login(self.student_one.user)

        response = self.client.get(reverse("academics_student_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Classes Held")
        self.assertContains(response, "2")
        self.assertContains(response, "50.0%")
        self.assertContains(response, "Own private note")
        self.assertNotContains(response, "Other student's note")


class DoubtForumTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="forum-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-FORUM-1"
        )
        self.student_class = Class.objects.create(
            name="9", section="A", academic_year="2026-27"
        )
        self.other_class = Class.objects.create(
            name="9", section="B", academic_year="2026-27"
        )
        self.subject = Subject.objects.create(name="Maths", code="MATH-FORUM")
        TeachingAssignment.objects.create(
            teacher=self.teacher,
            student_class=self.student_class,
            subject=self.subject,
        )
        self.student = self.make_student("forum-student", "F-1", self.student_class)
        self.classmate = self.make_student("forum-classmate", "F-2", self.student_class)
        self.outsider = self.make_student("forum-outsider", "F-3", self.other_class)

    def make_student(self, username, roll_number, student_class):
        user = User.objects.create_user(
            username=username, password="test-pass", role=User.Role.STUDENT
        )
        return StudentProfile.objects.create(
            user=user, roll_number=roll_number, student_class=student_class
        )

    def make_thread(self, student=None, student_class=None):
        return DoubtThread.objects.create(
            title="How do fractions work?",
            content="Please explain the common denominator.",
            student=student or self.student,
            student_class=student_class or self.student_class,
            subject=self.subject,
            is_public=True,
        )

    def test_student_can_create_thread_for_class_subject(self):
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("doubt_threads"), {
            "student_class": self.student_class.pk,
            "subject": self.subject.pk,
            "title": "Help with fractions",
            "content": "How do I find a common denominator?",
            "category": DoubtThread.Category.SYLLABUS_TOPIC,
        })
        thread = DoubtThread.objects.get(title="Help with fractions")
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertEqual(thread.student, self.student)
        self.assertEqual(thread.student_class, self.student_class)
        self.assertFalse(thread.is_public)

    def test_private_doubt_is_visible_to_author_and_assigned_teacher_only(self):
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("doubt_threads"), {
            "student_class": self.student_class.pk,
            "subject": self.subject.pk,
            "title": "Private homework question",
            "content": "I need help with question 4.",
            "category": DoubtThread.Category.ASSIGNMENT_HOMEWORK,
        })
        thread = DoubtThread.objects.get(title="Private homework question")
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertFalse(thread.is_public)

        self.client.force_login(self.classmate.user)
        self.assertNotContains(self.client.get(reverse("doubt_threads")), thread.title)
        self.assertEqual(self.client.get(reverse("doubt_thread_detail", args=[thread.pk])).status_code, 403)

        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(reverse("doubt_thread_detail", args=[thread.pk])).status_code, 200)
        self.client.force_login(self.teacher_user)
        self.assertContains(self.client.get(reverse("doubt_threads")), thread.title)
        self.assertEqual(self.client.get(reverse("doubt_thread_detail", args=[thread.pk])).status_code, 200)

    def test_public_doubt_is_visible_anonymously_to_classmates(self):
        self.client.force_login(self.student.user)
        self.client.post(reverse("doubt_threads"), {
            "student_class": self.student_class.pk,
            "subject": self.subject.pk,
            "title": "Public topic question",
            "content": "Can someone explain this topic?",
            "category": DoubtThread.Category.SYLLABUS_TOPIC,
            "privacy": "PUBLIC",
            "document_link": "https://example.com/physics-notes",
        })
        thread = DoubtThread.objects.get(title="Public topic question")
        self.assertTrue(thread.is_public)
        self.assertEqual(thread.document_link, "https://example.com/physics-notes")

        self.client.force_login(self.classmate.user)
        feed = self.client.get(reverse("doubt_threads"))
        detail = self.client.get(reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertContains(feed, thread.title)
        self.assertContains(feed, "Anonymous")
        self.assertNotContains(feed, self.student.user.username)
        self.assertContains(detail, "Anonymous")
        self.assertNotContains(detail, self.student.user.username)

        self.client.force_login(self.teacher_user)
        self.assertContains(self.client.get(reverse("doubt_thread_detail", args=[thread.pk])), self.student.user.username)

    def test_private_doubt_attachment_is_protected_by_thread_visibility(self):
        thread = self.make_thread()
        thread.is_public = False
        thread.save(update_fields=["is_public"])
        attachment = DoubtAttachment.objects.create(
            thread=thread,
            file=SimpleUploadedFile("diagram.png", b"image-bytes", content_type="image/png"),
        )
        url = reverse("doubt_attachment_download", args=[attachment.pk])

        self.client.force_login(self.classmate.user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_doubt_form_rejects_unsupported_attachment_types(self):
        self.client.force_login(self.student.user)
        response = self.client.post(
            reverse("doubt_threads"),
            {
                "student_class": self.student_class.pk,
                "subject": self.subject.pk,
                "title": "Unsupported attachment",
                "content": "This should be rejected.",
                "category": DoubtThread.Category.STUDY_RESOURCE,
                "privacy": "PRIVATE",
                "attachments": SimpleUploadedFile("script.exe", b"not allowed"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attach only PNG, JPG, JPEG, or PDF files.")
        self.assertFalse(DoubtThread.objects.filter(title="Unsupported attachment").exists())

    def test_teacher_inbox_filters_assigned_doubts_and_shows_real_student_identity(self):
        visible = self.make_thread()
        visible.title = "Visible homework doubt"
        visible.category = DoubtThread.Category.ASSIGNMENT_HOMEWORK
        visible.is_public = True
        visible.save()
        hidden = self.make_thread(student=self.outsider, student_class=self.other_class)
        hidden.title = "Unassigned class doubt"
        hidden.save()

        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("doubt_threads"), {
            "category": DoubtThread.Category.ASSIGNMENT_HOMEWORK,
            "student_class": self.student_class.pk,
            "student": self.student.pk,
            "status": "ALL",
            "date_range": "ALL",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, visible.title)
        self.assertContains(response, self.student.user.username)
        self.assertNotContains(response, hidden.title)

    def test_assigned_teacher_can_set_doubt_in_progress_and_attach_reply_files(self):
        thread = self.make_thread()
        self.client.force_login(self.teacher_user)

        status_response = self.client.post(
            reverse("doubt_thread_detail", args=[thread.pk]),
            {"action": "update_status", "status": DoubtThread.Status.IN_PROGRESS},
        )
        thread.refresh_from_db()
        self.assertEqual(status_response.status_code, 302)
        self.assertEqual(thread.status, DoubtThread.Status.IN_PROGRESS)

        reply_response = self.client.post(
            reverse("doubt_thread_detail", args=[thread.pk]),
            {
                "action": "reply",
                "content": "Please see the attached worked solution.",
                "attachments": SimpleUploadedFile("solution.pdf", b"%PDF-demo", content_type="application/pdf"),
            },
        )
        self.assertEqual(reply_response.status_code, 302)
        reply = DoubtReply.objects.get(thread=thread)
        self.assertTrue(reply.is_teacher_reply)
        self.assertEqual(reply.attachments.count(), 1)

    def test_unassigned_teacher_cannot_change_doubt_status(self):
        thread = self.make_thread()
        other_user = User.objects.create_user(
            username="forum-status-other", password="test-pass", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=other_user, employee_id="T-FORUM-STATUS")
        self.client.force_login(other_user)

        response = self.client.post(
            reverse("doubt_thread_detail", args=[thread.pk]),
            {"action": "update_status", "status": DoubtThread.Status.RESOLVED},
        )

        self.assertEqual(response.status_code, 403)
        thread.refresh_from_db()
        self.assertEqual(thread.status, DoubtThread.Status.OPEN)

    def test_student_cannot_create_thread_for_another_class(self):
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("doubt_threads"), {
            "student_class": self.other_class.pk,
            "subject": self.subject.pk,
            "title": "Out of class",
            "content": "This should not be saved.",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DoubtThread.objects.exists())

    def test_classmate_and_assigned_teacher_can_reply(self):
        thread = self.make_thread()
        self.client.force_login(self.classmate.user)
        response = self.client.post(reverse("doubt_thread_detail", args=[thread.pk]), {
            "action": "reply", "content": "Try converting to eighths."
        })
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertFalse(DoubtReply.objects.get().is_teacher_reply)

        self.client.force_login(self.teacher_user)
        response = self.client.post(reverse("doubt_thread_detail", args=[thread.pk]), {
            "action": "reply", "content": "Here is a worked example."
        })
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertTrue(DoubtReply.objects.get(user=self.teacher_user).is_teacher_reply)

    def test_other_class_cannot_view_thread(self):
        thread = self.make_thread()
        self.client.force_login(self.outsider.user)
        response = self.client.get(reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertEqual(response.status_code, 403)

    def test_teacher_must_be_assigned_to_thread_subject(self):
        thread = self.make_thread()
        another_teacher_user = User.objects.create_user(
            username="forum-other-teacher", password="test-pass", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(
            user=another_teacher_user, employee_id="T-FORUM-2"
        )
        self.client.force_login(another_teacher_user)
        response = self.client.get(reverse("doubt_thread_detail", args=[thread.pk]))
        self.assertEqual(response.status_code, 403)

    def test_author_can_toggle_resolved_status(self):
        thread = self.make_thread()
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("doubt_thread_detail", args=[thread.pk]), {
            "action": "resolve"
        })
        self.assertRedirects(response, reverse("doubt_thread_detail", args=[thread.pk]))
        thread.refresh_from_db()
        self.assertEqual(thread.status, DoubtThread.Status.RESOLVED)


class AnalyticsDashboardTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="analytics-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-ANALYTICS-1"
        )
        self.other_teacher_user = User.objects.create_user(
            username="analytics-other-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.other_teacher = TeacherProfile.objects.create(
            user=self.other_teacher_user, employee_id="T-ANALYTICS-2"
        )
        self.student_user = User.objects.create_user(
            username="analytics-student", password="test-pass", role=User.Role.STUDENT
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user, roll_number="A-1"
        )
        self.class_one = Class.objects.create(name="10", section="A", academic_year="2026-27")
        self.class_two = Class.objects.create(name="10", section="B", academic_year="2026-27")
        self.student.student_class = self.class_one
        self.student.save(update_fields=["student_class"])
        self.subject_math = Subject.objects.create(name="Mathematics", code="AN-MATH")
        self.subject_science = Subject.objects.create(name="Science", code="AN-SCI")
        TeachingAssignment.objects.create(
            teacher=self.teacher, student_class=self.class_one, subject=self.subject_math
        )
        TeachingAssignment.objects.create(
            teacher=self.teacher, student_class=self.class_one, subject=self.subject_science
        )
        TeachingAssignment.objects.create(
            teacher=self.other_teacher, student_class=self.class_two, subject=self.subject_math
        )

    def make_assessment(self, title, subject, total_marks, teacher=None, student_class=None):
        return Assessment.objects.create(
            title=title,
            teacher=teacher or self.teacher,
            student_class=student_class or self.class_one,
            subject=subject,
            assessment_type=Assessment.AssessmentType.TEST,
            total_marks=total_marks,
            is_published=True,
        )

    def add_result(self, assessment, student, marks_awarded, question=None):
        question = question or Question.objects.create(
            assessment=assessment,
            question_text="Solve the problem",
            question_type=Question.QuestionType.NUMERICAL,
            marks=assessment.total_marks,
            order=1,
        )
        attempt = AssessmentAttempt.objects.create(
            assessment=assessment,
            student=student,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            status=AssessmentAttempt.Status.SUBMITTED,
        )
        StudentAnswer.objects.create(
            attempt=attempt, question=question, awarded_marks=marks_awarded
        )
        return attempt

    def test_student_analytics_uses_weighted_subject_and_overall_scores(self):
        math_test = self.make_assessment("Algebra Test", self.subject_math, 10)
        science_test = self.make_assessment("Science Test", self.subject_science, 20)
        self.make_assessment("Not Taken", self.subject_math, 5)
        self.add_result(math_test, self.student, 8)
        self.add_result(science_test, self.student, 6)

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["taken_count"], 2)
        self.assertEqual(response.context["assigned_count"], 3)
        self.assertAlmostEqual(float(response.context["average_percentage"]), 46.666, places=2)
        self.assertEqual(response.context["highest_subject"]["subject"], self.subject_math)
        self.assertEqual(response.context["lowest_subject"]["subject"], self.subject_science)
        self.assertContains(response, "Algebra Test")
        self.assertContains(response, "Science Test")

    def test_anonymous_analytics_redirects_to_the_configured_login_page(self):
        response = self.client.get(reverse("student_analytics"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('student_analytics')}",
        )
        legacy_login = self.client.get("/accounts/login/?next=/academics/student/analytics/")
        self.assertEqual(legacy_login.status_code, 200)
        self.assertContains(legacy_login, "Login")

    def test_student_analytics_is_private_and_for_student_role_only(self):
        other_student_user = User.objects.create_user(
            username="analytics-student-two", password="test-pass", role=User.Role.STUDENT
        )
        other_student = StudentProfile.objects.create(
            user=other_student_user, roll_number="A-2", student_class=self.class_one
        )
        assessment = self.make_assessment("Private Result", self.subject_math, 10)
        self.add_result(assessment, other_student, 9)
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private Result")

        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("student_analytics"))
        self.assertEqual(response.status_code, 403)

    def test_teacher_analytics_calculates_class_item_and_attention_metrics(self):
        second_student_user = User.objects.create_user(
            username="analytics-student-three", password="test-pass", role=User.Role.STUDENT
        )
        second_student = StudentProfile.objects.create(
            user=second_student_user, roll_number="A-3", student_class=self.class_one
        )
        assessment = self.make_assessment("Class Quiz", self.subject_math, 10)
        question = Question.objects.create(
            assessment=assessment,
            question_text="Find x",
            question_type=Question.QuestionType.NUMERICAL,
            marks=10,
            order=1,
        )
        self.add_result(assessment, self.student, 10, question=question)
        self.add_result(assessment, second_student, 4, question=question)
        self.client.force_login(self.teacher_user)

        response = self.client.get(reverse("teacher_analytics"), {
            "student_class": self.class_one.pk,
            "assessment": assessment.pk,
            "threshold": "50",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submissions"], 2)
        self.assertEqual(response.context["enrolled_count"], 2)
        self.assertAlmostEqual(float(response.context["average_percentage"]), 70.0, places=1)
        self.assertEqual(float(response.context["highest_score"]), 10.0)
        self.assertEqual(float(response.context["lowest_score"]), 4.0)
        self.assertEqual(len(response.context["needs_attention"]), 1)
        self.assertEqual(float(response.context["item_analysis"][0]["correct_percentage"]), 50.0)

    def test_teacher_analytics_rejects_unassigned_class_and_assessment(self):
        own_assessment = self.make_assessment("Assigned", self.subject_math, 10)
        foreign_assessment = self.make_assessment(
            "Foreign", self.subject_math, 10,
            teacher=self.other_teacher, student_class=self.class_two,
        )
        self.client.force_login(self.teacher_user)
        class_response = self.client.get(reverse("teacher_analytics"), {
            "student_class": self.class_two.pk,
        })
        assessment_response = self.client.get(reverse("teacher_analytics"), {
            "student_class": self.class_one.pk,
            "assessment": foreign_assessment.pk,
        })
        self.assertEqual(class_response.status_code, 403)
        self.assertEqual(assessment_response.status_code, 403)


class SeedDataCommandTests(TestCase):
    def test_seed_command_is_repeatable(self):
        call_command("seed_data", stdout=StringIO())
        call_command("seed_data", stdout=StringIO())

        self.assertEqual(User.objects.filter(username__in=["teacher1", "student1", "student2"]).count(), 3)
        self.assertEqual(Class.objects.filter(name="10", section="A", academic_year="2026-27").count(), 1)
        self.assertEqual(Subject.objects.filter(code__in=["SEED-MATH", "SEED-SCI"]).count(), 2)
        self.assertEqual(Assessment.objects.filter(title="Sample Mathematics Assessment").count(), 1)
        self.assertEqual(Timetable.objects.count(), 2)
        self.assertTrue(User.objects.filter(username="parent1", role=User.Role.PARENT).exists())
        self.assertEqual(
            StudentProfile.objects.get(user__username="student1").parent.user.username,
            "parent1",
        )


class TimetableAccessTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="schedule-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user, employee_id="T-SCHEDULE"
        )
        self.student_class = Class.objects.create(
            name="7", section="A", academic_year="2026-27"
        )
        self.other_class = Class.objects.create(
            name="7", section="B", academic_year="2026-27"
        )
        self.subject = Subject.objects.create(name="History", code="HISTORY-SCHEDULE")
        TeachingAssignment.objects.create(
            teacher=self.teacher, student_class=self.student_class, subject=self.subject
        )
        self.own_entry = Timetable.objects.create(
            student_class=self.student_class,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=Timetable.DayOfWeek.MONDAY,
            start_time="09:00",
            end_time="09:45",
            room_number="204",
        )
        self.other_entry = Timetable.objects.create(
            student_class=self.other_class,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=Timetable.DayOfWeek.TUESDAY,
            start_time="10:00",
            end_time="10:45",
        )
        self.student_user = User.objects.create_user(
            username="schedule-student", password="test-pass", role=User.Role.STUDENT
        )
        StudentProfile.objects.create(
            user=self.student_user, roll_number="S-SCHEDULE", student_class=self.student_class
        )

    def test_student_only_sees_timetable_for_own_class(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_timetable"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "History")
        self.assertContains(response, "Room 204")
        self.assertNotContains(response, str(self.other_class))

    def test_teacher_sees_only_assigned_class_subject_slots(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("teacher_timetable"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "History")
        self.assertContains(response, str(self.student_class))
        self.assertNotContains(response, str(self.other_class))

    def test_roles_cannot_open_the_other_role_timetable(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("teacher_timetable"))
        self.assertRedirects(response, reverse("dashboard"))


class ParentReadOnlyAccessTests(TestCase):
    def setUp(self):
        self.parent_user = User.objects.create_user(
            username="linked-parent", password="test-pass", role=User.Role.PARENT
        )
        self.parent = ParentProfile.objects.create(user=self.parent_user)
        self.student_user = User.objects.create_user(
            username="linked-child", password="test-pass", role=User.Role.STUDENT
        )
        self.student_class = Class.objects.create(
            name="8", section="A", academic_year="2026-27"
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            roll_number="P-CHILD",
            student_class=self.student_class,
            parent=self.parent,
        )
        self.other_class = Class.objects.create(
            name="8", section="B", academic_year="2026-27"
        )
        teacher_user = User.objects.create_user(
            username="parent-view-teacher", password="test-pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            user=teacher_user, employee_id="T-PARENT-VIEW"
        )
        self.subject = Subject.objects.create(name="Geography", code="GEO-PARENT-VIEW")
        TeachingAssignment.objects.create(
            teacher=self.teacher, student_class=self.student_class, subject=self.subject
        )
        self.entry = Timetable.objects.create(
            student_class=self.student_class,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=Timetable.DayOfWeek.THURSDAY,
            start_time="11:00",
            end_time="11:45",
            room_number="305",
        )
        self.resource = Resource.objects.create(
            title="Geography notes",
            teacher=self.teacher,
            student_class=self.student_class,
            subject=self.subject,
            file="resources/geography.pdf",
        )
        self.foreign_resource = Resource.objects.create(
            title="Private class notes",
            teacher=self.teacher,
            student_class=self.other_class,
            subject=self.subject,
            file="resources/private.pdf",
        )
        self.thread = DoubtThread.objects.create(
            title="Map scale question",
            content="How do I calculate map scale?",
            student=self.student,
            student_class=self.student_class,
            subject=self.subject,
            is_public=True,
        )
        self.client.force_login(self.parent_user)

    def test_parent_can_read_linked_child_pages_and_only_scoped_content(self):
        private_thread = DoubtThread.objects.create(
            title="Private child question",
            content="This must stay private.",
            student=self.student,
            student_class=self.student_class,
            subject=self.subject,
        )
        dashboard = self.client.get(reverse("dashboard"))
        timetable = self.client.get(reverse("parent_timetable"))
        analytics = self.client.get(reverse("parent_analytics"))
        resources = self.client.get(reverse("resource_list"))
        discussions = self.client.get(reverse("doubt_threads"))
        detail = self.client.get(reverse("doubt_thread_detail", args=[self.thread.pk]))

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Student Progress")
        self.assertContains(dashboard, "View Timetable")
        self.assertContains(dashboard, "View Resources")
        self.assertContains(dashboard, "View Discussions")
        self.assertEqual(timetable.status_code, 200)
        self.assertContains(timetable, "Geography")
        self.assertEqual(analytics.status_code, 200)
        self.assertContains(analytics, "Student Progress")
        self.assertEqual(resources.status_code, 200)
        self.assertContains(resources, "Geography notes")
        self.assertNotContains(resources, "Private class notes")
        self.assertEqual(discussions.status_code, 200)
        self.assertContains(discussions, "Map scale question")
        self.assertFalse(discussions.context["can_create_thread"])
        self.assertNotContains(discussions, private_thread.title)
        self.assertEqual(self.client.get(reverse("doubt_thread_detail", args=[private_thread.pk])).status_code, 403)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "read-only access")
        self.assertNotContains(detail, 'name="action" value="reply"')

    def test_parent_cannot_access_an_unlinked_students_data(self):
        response = self.client.get(
            reverse("parent_timetable"), {"student_id": self.student.pk + 1000}
        )
        foreign_thread = DoubtThread.objects.create(
            title="Other class question",
            content="Private",
            student=self.student,
            student_class=self.other_class,
            subject=self.subject,
        )
        thread_response = self.client.get(
            reverse("doubt_thread_detail", args=[foreign_thread.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(thread_response.status_code, 403)

    def test_parent_posts_are_forbidden_and_do_not_change_data(self):
        thread_response = self.client.post(reverse("doubt_threads"), {
            "student_class": self.student_class.pk,
            "subject": self.subject.pk,
            "title": "Should not be created",
            "content": "No write access",
        })
        reply_response = self.client.post(
            reverse("doubt_thread_detail", args=[self.thread.pk]),
            {"action": "reply", "content": "Should not be posted"},
        )
        upload_response = self.client.post(reverse("resource_upload"), {
            "title": "Should not upload",
        })
        self.assertEqual(thread_response.status_code, 403)
        self.assertEqual(reply_response.status_code, 403)
        self.assertEqual(upload_response.status_code, 403)
        self.assertEqual(DoubtThread.objects.count(), 1)
        self.assertEqual(DoubtReply.objects.count(), 0)
        self.assertEqual(Resource.objects.count(), 2)
