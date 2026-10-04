# Study_Pod

Study_Pod is a Django school portal for teachers, students, and parents. It uses Django 6.1.1, a custom `accounts.User`, and SQLite by default.

## Architecture

- **`accounts`** manages authentication, role-based profiles, dashboards, notices, and assessment setup.
- **`academics`** manages classes, subjects, teaching assignments, attendance, discussions, and performance analytics.
- **`exam_engine`** manages assessment questions and options, attempt timing and restrictions, answer saving, automatic grading, and teacher evaluation of short answers.
- **`study_pod`** contains project settings and root URL configuration.

Students are associated with a class through `StudentProfile`. Teacher access to class and subject work is scoped through `TeachingAssignment`. Assessments and attempts are scoped to those profiles in their views.

## Local Setup (PowerShell)

Run these commands from the directory containing `manage.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "Django==6.1.1" Pillow
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

Open <http://127.0.0.1:8000/login/>. The administration site is at <http://127.0.0.1:8000/admin/>. Create an administrator when needed:

```powershell
python manage.py createsuperuser
```

### Demo Accounts

`seed_data` creates or refreshes these local development accounts, their profiles, a class, two subjects, teaching assignments, and a draft sample assessment:

| Role | Username | Password |
| --- | --- | --- |
| Teacher | `Teacher1` | `Teacher@12345` |
| Student | `Student1` | `Student@12345` |
| Parent  | `Parent1` | `Parent@12345` |

These predictable credentials are for local development only. Do not expose them or reuse them in a deployed environment. The sample assessment is a draft and has no questions until a teacher adds them.

## Environment Configuration

For convenience, local development defaults to `DEBUG=True`, a development-only secret key, and local allowed hosts. Configure these variables explicitly for deployment:

| Variable | Purpose | Production example |
| --- | --- | --- |
| `SECRET_KEY` | Django signing and cryptographic key | A unique, randomly generated secret |
| `DEBUG` | Enables/disables debug pages | `False` |
| `ALLOWED_HOSTS` | Comma-separated hostnames accepted by Django | `portal.example.com,www.portal.example.com` |

Generate a secret key with:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the values in the deployment environment or PowerShell session, rather than committing secrets to source control:

```powershell
$env:SECRET_KEY = "paste-a-generated-secret-here"
$env:DEBUG = "False"
$env:ALLOWED_HOSTS = "portal.example.com,www.portal.example.com"
```

When `DEBUG=False`, Django refuses to start if `SECRET_KEY` is missing. Set `ALLOWED_HOSTS` to the exact public hostnames. Use a production WSGI/ASGI server and a correctly configured HTTPS reverse proxy; do not use `runserver` in production.

Static files use `STATIC_ROOT = staticfiles/` and should be collected for deployment:

```powershell
python manage.py collectstatic --noinput
```

Uploaded files are stored under `MEDIA_ROOT = media/` and served at `MEDIA_URL = /media/` according to the deployment's media-storage configuration. Configure durable, backed-up storage and serve uploads through the web server or a dedicated object-storage service in production.

SQLite is configured by default for local use. Configure a production database and backups separately before deploying a multi-user production instance.

## Database Seeding

The seed command is safe to run repeatedly and wraps its database updates in a transaction:

```powershell
python manage.py seed_data
```

It creates or refreshes the demo identities `teacher1`, `student1`, and `student2`, class `10-A` for academic year `2026-27`, Mathematics and Science, teacher assignments for both subjects, and a draft Mathematics assessment.

## Tests and Checks

Run the full test suite and Django system checks with:

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Main URLs

- `/login/`, `/dashboard/`, `/profile/`
- `/academics/teacher/attendance/`, `/academics/student/attendance/`
- `/academics/discussions/`
- `/academics/student/analytics/`, `/academics/teacher/analytics/`
- `/exam/tests/` for teacher assessment management
- `/exam/student/assessments/` for student assessments
- `/admin/` for Django administration
