from django.urls import path

from . import views


urlpatterns = [
    path(
        "suggest-questions/",
        views.suggest_related_questions,
        name="suggest_related_questions",
    ),
    path(
        "teacher/questions/",
        views.teacher_question_suggestions,
        name="teacher_question_suggestions",
    ),
    path(
        "student/recommendations/",
        views.student_study_recommendations,
        name="student_study_recommendations",
    ),
    path(
        "resource-web-search/",
        views.resource_web_search,
        name="resource_web_search",
    ),
    path(
        "resource/<int:resource_id>/related/",
        views.resource_related_material,
        name="resource_related_material",
    ),
]
