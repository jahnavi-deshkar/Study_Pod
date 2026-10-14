# Study_Pod Project Handover

**Prepared:** 14 October 2026  

Use this folder for all continued work. Do not switch back to Study_Pod(update) unless asked.

## Project at a glance

Study_Pod is a Django school portal for **teachers, students, and parents**. It uses a custom accounts.User model and SQLite by default. Main Django apps:

- **accounts/** — authentication, role profiles, dashboards, linked parent/student profiles, and profile settings.
- **academics/** — classes, subjects, teacher assignments, attendance, doubts/discussions, timetable, notices/resources, and analytics.
- **exam_engine/** — assessment question creation, student attempts, timing, answer handling, grading, and teacher review.
- **study_pod/** — settings and root URL configuration.

The README documents Django 6.1.1 and Pillow. There is no requirements.txt at the project root, so the README install command is the current dependency guide. Verify the Python/Django versions in the environment you use before installing packages.

## Existing portal capabilities

### Student portal

- Role-based dashboard and class-scoped academic information.
- Attendance and timetable views for the student's class.
- Published assessments, test instructions, attempts, and results according to assessment settings.
- Student analytics.
- Doubt/discussion creation and replies.
- Optional profile photo upload.

### Parent portal

- Parent profile can link to students.
- Parent views are read-only and scoped to linked children.
- Attendance, timetable, analytics, and public class discussion information are scoped to the selected/linked child. Private doubts are not exposed to parents.

### Teacher portal

- Work is scoped by TeachingAssignment (teacher + class + subject).
- Attendance management and teacher timetable.
- Class/subject assessment management, question creation, test preview, and student attempt/answer review.
- Doubt Resolution Inbox and replies (details below).

## Doubts workflow changes

The student doubt form includes required subject, category, title, and content; category choices are Syllabus / Topic, Assignment / Homework, Notice / Announcement, and Study Resource. Students can optionally attach a document link and PNG/JPG/JPEG/PDF files (10 MB per file). Privacy defaults to **Private**; public doubts appear anonymously to classmates.

Attachments are stored privately and served through a permission-checked download view. The teacher view displays the real student identity, class, category, privacy, timestamp, snippet, and attachment indicator. Teachers can filter by category, assigned class/batch, student, subject, date range, status, or search text. Teachers can reply with text and file attachments and set a doubt to Open, In Progress, or Resolved. Student profile photos can be uploaded from the profile page and appear in the teacher inbox.

Important implementation locations:

- academics/models.py — doubt fields, status, replies, and attachments.
- academics/forms.py — student submission, teacher inbox filters, and reply forms.
- academics/views.py — privacy/access scoping, inbox filtering, status updates, reply handling, and protected attachment download.
- academics/templates/academics/doubt_threads.html — student feed and teacher inbox.
- academics/templates/academics/doubt_thread_detail.html — doubt detail, replies, and status controls.
- academics/storage.py — private doubt attachment storage.
- accounts/models.py, accounts/forms.py, accounts/views.py, and accounts/templates/accounts/profile.html — student photo field and upload UI.

## Assessment marks validation changes

Assessment total marks are entered when the assessment is created. The question editor now:

- Shows a sticky live counter for allocated question marks versus configured test marks.
- Recalculates the preview as a new question is authored or saved question marks are edited.
- Shows a warning with the shortfall or excess.
- Lists saved questions so teachers can update marks or delete a question; the displayed total recalculates after changes.
- Keeps an unpublished assessment as a draft while marks differ.

The preview displays the mismatch and opens a confirmation modal when the teacher tries to publish. Options are **Go Back & Fix** and **Auto-Update Total Marks**. **Proceed Anyway** is only shown when strict validation is disabled. The server also checks the mismatch before publishing, so bypassing the browser modal does not bypass strict validation.

Strict mode is enabled by default in study_pod/settings.py:

    ASSESSMENT_MARKS_STRICT = True

An administrator/developer can set it to False in settings to allow the explicit Proceed Anyway option. Assessments are assigned to a class/batch when created; publishing makes them available to students in that class. There is no separate batch-assignment action in the current workflow.

Relevant files:

- exam_engine/views.py — question mark edit/delete, server-side sum and publish guard, auto-update action.
- exam_engine/templates/exam_engine/question_create.html — sticky counter, live warnings, saved-question controls.
- exam_engine/templates/exam_engine/test_preview.html — totals, mismatch alert, publish modal.
- study_pod/settings.py — ASSESSMENT_MARKS_STRICT setting.

All saved questions currently count toward the assessment total. The project does not currently model optional/bonus questions or “attempt N out of M” scoring; decide how those should affect the total before adding that feature.

## Configuration and repository housekeeping

- `study_pod/settings.py` sets `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`, which resolved the Django W042 warnings about auto-created model primary keys.
- The root `.gitignore` already ignores `__pycache__/`, `*.pyc`, and `*.pyo`. If a cache file is already tracked by Git, ignoring it alone is not enough; remove it from the index with `git rm --cached` while preserving the local file.
- The project root does not currently contain a `requirements.txt`; dependency installation is documented in README.md.

## Database migrations

Doubt submission, teacher resolution, and profile-photo migrations are:

- academics/migrations/0014_doubt_submission_workflow.py
- academics/migrations/0015_doubt_in_progress_and_reply_attachments.py
- accounts/migrations/0003_studentprofile_profile_picture.py

Run python manage.py migrate after pulling/copying changes into a new environment. The latest transfer to this folder applied these migrations to its SQLite database.

## Local setup

From the folder containing manage.py, use PowerShell:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install "Django==6.1.1" Pillow
    python manage.py migrate
    python manage.py seed_data
    python manage.py runserver

Open http://127.0.0.1:8000/login/. Create an administrator with python manage.py createsuperuser if needed.

seed_data creates local development demo accounts:

| Role | Username | Password |
| --- | --- | --- |
| Teacher | Teacher1 | Teacher@12345 |
| Student | Student1 | Student@12345 |
| Parent | Parent1 | Parent@12345 |

These credentials are for local development only. Never use or expose them in a deployed system.

## Checks and current validation status

Useful commands:

    python manage.py check
    python manage.py makemigrations --check --dry-run
    python manage.py test

After the latest assessment-counter/modal changes, Django check, Python syntax parsing, and parsing of both changed Django templates passed. The full test suite was **not rerun after those latest UI/server-flow changes**. An earlier full run after the doubts/marks feature transfer reported 52 passing tests; rerun the full suite before treating the newest changes as fully regression-tested.

## Suggested next steps

1. Run the full test suite in this project folder and address any regressions from the latest marks editor and publish modal changes.
2. Manually exercise equal, under-allocated, and over-allocated totals in a browser; try editing/deleting saved marks, auto-updating the total, and publishing in both strict modes.
3. Decide whether optional/bonus questions are needed. If yes, define whether they count toward configured marks before adding the model/UI behavior.
4. If administrators need to toggle strict mode without editing code, add a persisted admin setting rather than relying on study_pod/settings.py.
5. If “Assign to Batch” should be a separate operation, design that flow; currently the class is chosen when the assessment is created and publication exposes it to that class.
6. Review db.sqlite3 before committing: it is currently reported as modified in the working tree and may contain local data/migration state.

## Useful URLs

- /login/, /dashboard/, /profile/
- /academics/teacher/attendance/, /academics/student/attendance/
- /academics/discussions/
- /academics/student/analytics/, /academics/teacher/analytics/
- /exam/tests/ (teacher assessment management)
- /exam/student/assessments/ (student assessments)
- /admin/ (Django administration)
