from django import forms

from academics.models import Assessment


class AssessmentConfigurationForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = (
            "max_attempts",
            "shuffle_questions",
            "show_results_immediately",
            "passmark_percentage",
            "access_code",
            "instructions",
        )
        widgets = {
            "max_attempts": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "shuffle_questions": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_results_immediately": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "passmark_percentage": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100", "step": "0.1"}),
            "access_code": forms.TextInput(attrs={"class": "form-control", "maxlength": "20", "autocomplete": "new-password"}),
            "instructions": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_passmark_percentage(self):
        value = self.cleaned_data["passmark_percentage"]
        if not 0 <= value <= 100:
            raise forms.ValidationError("Passmark must be between 0 and 100 percent.")
        return value
