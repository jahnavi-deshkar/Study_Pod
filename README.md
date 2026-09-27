# StudyPod

StudyPod is a Django school portal with Teacher, Student, and Parent accounts.

## Requirements

- Python
- Django 6.1.1

The project uses SQLite, which is included with Python. No separate database package is needed.

## Install and Run

Open PowerShell in the folder containing `manage.py`, then install Django:

```powershell
python -m pip install "Django==6.1.1"
```

Apply database migrations and start the development server:

```powershell
python manage.py migrate
python manage.py runserver
```

Open the login page at <http://127.0.0.1:8000/login/>. The Django admin is at <http://127.0.0.1:8000/admin/>. Create an administrator account first if needed:

```powershell
python manage.py createsuperuser
```

Stop the development server with `Ctrl+C` in the terminal. `DEBUG` is enabled for local development; do not use the development server or `DEBUG=True` in production.

## Local Test Data

Create these sample accounts and their profiles in Django admin. These credentials come from the supplied test-data image and are for local testing only; do not reuse them outside this project.

| Role | Username | Password | Profile data |
| --- | --- | --- | --- |
| Parent | `Parent1` | `Parent@12345` | Raj Sharma; phone `9999999999` |
| Student | `Student1` | `Student@12345` | Aman Sharma; roll number `10`; class `10-A`; parent Raj Sharma |
| Teacher | `Teacher1` | `Teacher@12345` | Anil Verma; employee ID `T001`; department Mathematics |

In `/admin/`, create a Class named `10`, section `A`, and set its academic year. Create a Mathematics subject with a unique subject code, then create a Teaching Assignment linking Teacher1, that class, and the subject. Set each user's role and password, create the corresponding profile, and link Student1 to the class and Raj Sharma's parent profile. The app does not automatically seed these sample records.

## Tests

Run Django's automated test discovery with:

```powershell
python manage.py test
```

The `accounts` and `academics` test modules currently contain placeholders, not automated test cases. Until automated tests are added, use these manual acceptance cases with the sample accounts above:

| ID | Test | Expected result |
| --- | --- | --- |
| TC01 | Log in as Parent1, Student1, and Teacher1 with each correct password. | Each account reaches the dashboard for its role. |
| TC02 | Log in with an incorrect password. | Login is rejected and an invalid-credentials message is shown. |
| TC03 | Open `/dashboard/` while logged out, then log in and log out. | Logged-out access redirects to login; logout returns to login. |
| TC04 | As Teacher1, open attendance, select the assigned class and a date, mark students present or absent, and save. | Attendance is saved for the selected date and can be viewed again. |
| TC05 | View attendance as Student1, then as Parent1. | Student1 sees their own records; Parent1 sees attendance for their linked student. |
| TC06 | As Teacher1, create a notice for the assigned class. View notices as Teacher1, Student1, and Parent1. | The teacher sees their notice, and the student and linked parent see notices for the student's class. |
| TC07 | As a Student or Parent, try to open teacher-only attendance marking and notice creation pages. | Access is redirected to that user's dashboard. |
| TC08 | Update profile details for each role and reload the profile page. | Valid profile changes are saved and shown after reload. |
