from django.apps import AppConfig


class AiSuggestionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ai_suggestions"

    def ready(self):
        import ai_suggestions.signals  # noqa: F401
