# Study_Pod

Study_Pod is a role-based Django learning portal built around a real coaching-academy workflow. Recruiters can explore teacher, student, and parent dashboards using the included demo database and study resources.

## Project overview

The project is split into focused Django apps:

- **`accounts`** handles authentication, role profiles, dashboards, notices, and resource pages.
- **`academics`** handles classes, subjects, teaching assignments, attendance, timetables, analytics, study resources, and student discussions.
- **`exam_engine`** handles assessments, questions, attempts, answer capture, scoring, and evaluation.
- **`ai_suggestions`** provides optional teacher and student study suggestions using local resource search and configured AI services.

Access is scoped by role and class: teachers work with assigned classes and subjects, students see their own class and progress, and parents have read-only access to linked children.

## Real-world dataset scale

The included SQLite demo database contains DSP Mathematics Academy data:

- 2 batches, 6 Mathematics subjects, and 180 students
- 30 tests (`T01`–`T30`) represented by 60 published batch assessments
- 5,187 evaluated attempts and 5,400 imported attendance records
- Notices, study resources, resolved and open student discussions, and teacher replies

The six source Excel workbooks are intentionally excluded from Git in `raw_data/`. The pre-populated `db.sqlite3` and downloadable resources under `media/resources/` are included for immediate local exploration.

## Recruiter demo logins

| Role | Username | Password | Demo profile |
| --- | --- | --- | --- |
| Teacher (Faculty Admin) | `teacher1` | `password123` | D.S.P. Sir; class analytics, 60 assessments, attendance, timetable, notices, resources, and Q&A moderation |
| Student (Morning Batch) | `m1` | `student123` | Shruti Sathe; 77.96% average across 28 attempts |
| Student (Evening Batch) | `e49` | `student123` | Aditi Agarkar; 74.74% average across 27 attempts |
| Parent (multi-child) | `parent1` | `password123` | Rajesh Sathe; switch between Shruti Sathe (`M1`) and Gaurav Sathe (`M8`) with read-only access |
| Parent (Evening Batch) | `parent_e49` | `password123` | Suresh Agarkar; linked to Aditi Agarkar (`E49`) |

These credentials are for this local demo database only. Replace them before using the application in a shared or deployed environment.

## Quickstart (Windows PowerShell)

Run from the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/login/> and sign in with any account above. The included database and `media/resources/` files provide the demo data; the source spreadsheets are not required for normal browsing.

## Useful commands

```powershell
# Run the full test suite
python manage.py test

# Check Django configuration
python manage.py check

# Rebuild the complete academy dataset from the six source workbooks in raw_data/
python manage.py setup_dsp_demo

# Use another workbook directory
python manage.py setup_dsp_demo --data-dir "D:\path\to\raw_data"
```

The data pipeline runs the roster, marks/attendance, and community imports in order. Each stage is safe to rerun. `raw_data/` is git-ignored because the source workbooks contain private student records.

## AI and offline behavior

Core dashboards and resource pages use the local database and files. They remain available when Hugging Face is unreachable; resource index status may show as unknown until the local embedding model is available. AI suggestions additionally require the embedding model and a configured `GROQ_API_KEY`.

For local AI suggestions, put configuration in an untracked `.env` file beside `manage.py`:

```dotenv
GROQ_API_KEY=your-key
GROQ_MODEL=qwen/qwen3.8-27b
```

The local Chroma index is stored in `chroma_db/` and can be rebuilt by reindexing resources after the embedding model has been downloaded. Do not commit API keys or student source workbooks.

## Project URLs

- `/login/` and `/dashboard/` — sign in and open the role-based dashboard
- `/notices/`, `/resources/`, and `/academics/discussions/` — academy community and learning materials
- `/academics/teacher/analytics/` and `/academics/student/analytics/` — progress views
- `/academics/teacher/timetable/`, `/academics/student/timetable/`, and `/academics/parent/timetable/` — weekly schedules
- `/exam/tests/` and `/exam/student/assessments/` — teacher assessment management and student assessments
- `/admin/` — Django administration

## Configuration and deployment

Local development defaults to `DEBUG=True` with a development-only secret key. For deployment, set `SECRET_KEY`, `DEBUG=False`, and an explicit comma-separated `ALLOWED_HOSTS`. Use a production WSGI/ASGI server, HTTPS, durable media storage, and a production database. Do not deploy with the demo credentials or use Django's `runserver` as a production server.
