# Study_Pod — Full-Stack Academic Portal & Timed Exam Engine (DSP’s Mathematics Academy)

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Django 5.x](https://img.shields.io/badge/Django-5.x-092E20?logo=django&logoColor=white)
![Deployed on Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-black?logo=vercel&logoColor=white)
![65 tests passing](https://img.shields.io/badge/Tests-65%20Passing-brightgreen)

> **Live Demo:** https://study-pod-ai.vercel.app/login/

Study_Pod is a role-based Django learning portal built around a real coaching-academy workflow. Explore teacher, student, and parent portals, plus a timed assessment engine, using the included demo database and study resources.

## Recruiter demo logins

Sign in at `/login/` with one of the preloaded accounts below. The credentials are for the bundled demo dataset.

| Role | Username | Password | What to Explore |
|---|---|---|---|
| **Teacher** | `teacher1` | `password123` | 180-student roster, test creation and grading, attendance marking, analytics, resource uploads |
| **Student** | `m1` | `student123` | Timed assessments, instant score breakdowns, timetable, attendance, study resources |
| **Parent (Multi-Child)** | `parent1` | `password123` | Multi-child switcher (`M1` and `M8`), read-only marks and attendance tracking, notices |

These credentials are intended only for the demo database. Change them before using a shared deployment.

## Dataset scale & domain highlights

The included SQLite database contains DSP Mathematics Academy data:

- **180** student profiles across two batches
- **60** published batch assessments across 30 tests, with their question banks
- **5,187** historical timed exam attempts
- **5,400** imported daily attendance records
- Study resources, leave request and review workflows, notices, and threaded doubt discussions with teacher replies

The six source Excel workbooks are intentionally excluded from Git because they contain private student records. The pre-populated `db.sqlite3` and downloadable files under `media/resources/` are included for immediate exploration; source spreadsheets are not needed for normal browsing.

## Key features & UI/UX architecture

- **Three role-based portals:** Server-side role and class scoping for Teachers, Students, and multi-child Parents. Parents have read-only access to linked children.
- **Assessment and timed exam engine:** Assessment authoring, question banks, timed student attempts, scoring, and result breakdowns.
- **Persistent zero-FOUC dark mode:** A synchronous `<head>` theme loader applies the saved `localStorage` preference or `prefers-color-scheme` before the page renders. CSS custom properties and native `color-scheme` controls support theme parity, with Chart.js colors synchronized when the theme changes.
- **Collapsible role-aware sidebar:** The 250px desktop sidebar collapses to a 68px icon rail and persists its state in `localStorage`. On mobile it becomes a slide-over drawer with Escape-to-close, active and nested route highlighting, and keyboard-friendly controls.
- **Contextual quick-back breadcrumbs:** Nested portal pages provide a Back action and Dashboard shortcut, so navigation does not depend on the browser's hardware Back button. The login screen and active timed exam view (`student_test`) stay distraction-free.
- **Responsive analytics and portal pages:** Attendance, schedules, notices, study materials, leave workflows, and threaded doubt discussions are available in role-appropriate views.

## Vercel serverless architecture

- **Python runtime:** `vercel.json` configures the `@vercel/python` function and explicitly bundles `db.sqlite3` and `media/**` with `includeFiles`.
- **Writable SQLite at runtime:** When running on Vercel without `DATABASE_URL`, the bundled SQLite file is copied to `/tmp/db.sqlite3` so login and exam session writes can succeed in the serverless environment. Vercel's `/tmp` storage is temporary and is not a durable database for ongoing production data.
- **Static and media files:** WhiteNoise with `CompressedStaticFilesStorage` serves static assets. The Django URL configuration serves bundled `/media/` files when `DEBUG=False`.
- **Bundle hygiene:** Optional ML/vector dependencies such as `chromadb` and `sentence-transformers` are imported lazily where needed, keeping them out of the normal serverless startup path and helping the deployment stay within Vercel's function bundle limit.
- **Deployment configuration:** Set `SECRET_KEY`, `DEBUG=False`, and the required host/CSRF environment values in Vercel. Keep API keys and private student source files out of Git.

## Local setup & verification

Requirements: Python 3.11 or newer and Git.

Clone the repository, activate the virtual environment, install dependencies, and start Django:

```powershell
git clone https://github.com/YOUR-USERNAME/Study_Pod--AI-.git
cd Study_Pod--AI-
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/login/> and use one of the demo accounts above. The bundled database and `media/resources/` provide the sample data.

Run the full suite (**65/65 passing tests**, including `VercelDeploymentReadinessTests` under `DEBUG=False`) and check the Django configuration:

```powershell
python manage.py test
python manage.py check
```

Additional data setup commands, for maintainers with access to the excluded workbooks:

```powershell
# Rebuild the demo data from the six source workbooks in raw_data/
python manage.py setup_dsp_demo

# Use another workbook directory
python manage.py setup_dsp_demo --data-dir "D:\path\to\raw_data"
```

The data pipeline imports the roster, marks and attendance, and community data in order. Each stage is safe to rerun. `raw_data/` is git-ignored because the source workbooks contain private student records.

## Project structure

- **`accounts/`** — Authentication, role profiles, dashboards, notices, and resource pages
- **`academics/`** — Classes, subjects, teaching assignments, attendance, timetables, analytics, study resources, and student discussions
- **`exam_engine/`** — Assessments, questions, attempts, answer capture, scoring, and evaluation
- **`ai_suggestions/`** — Optional teacher and student study suggestions using local resource search and configured AI services
- **`study_pod/`** — Django project settings, root URL configuration, and WSGI entry point
- **`media/resources/`** — Bundled downloadable study resources

Access is scoped by role and class: teachers work with assigned classes and subjects, students see their own class and progress, and parents have read-only access to linked children.

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

## Configuration notes

Local development defaults to `DEBUG=True` with a development-only secret key. For deployment, configure `SECRET_KEY`, `DEBUG=False`, and explicit comma-separated `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` values. Do not use Django's `runserver` as a production server. The included SQLite database and demo credentials are for demonstration; use a durable production database for ongoing deployment data.
