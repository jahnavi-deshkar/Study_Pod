from django.urls import path

from . import views


urlpatterns = [

    # Teacher
    path(
        "tests/",
        views.test_management,
        name="test_management"
    ),

    path(
        "assessments/<int:assessment_id>/questions/create/",
        views.question_create,
        name="question_create"
    ),

    path(
        "assessments/<int:assessment_id>/preview/",
        views.test_preview,
        name="test_preview"
    ),


    # Student
    path(
        "student/assessments/",
        views.student_assessments,
        name="student_assessments"
    ),

    path(
        "student/assessments/<int:assessment_id>/instructions/",
        views.student_assessment_instructions,
        name="student_assessment_instructions"
    ),

    path(
        "student/assessments/<int:assessment_id>/test/",
        views.student_test,
        name="student_test"
    ),

    path(
        "student/assessments/<int:assessment_id>/submit/",
        views.student_submit,
        name="student_submit"
    ),

    path(
        "student/assessments/<int:assessment_id>/result/",
        views.student_result,
        name="student_result"
    ),

    path(
        "tests/<int:assessment_id>/attempts/",
        views.teacher_attempts,
        name="teacher_attempts"
    ),
    path(
        "tests/<int:assessment_id>/attempts/<int:attempt_id>/",
        views.teacher_attempt_detail,
        name="teacher_attempt_detail"
    ),
]