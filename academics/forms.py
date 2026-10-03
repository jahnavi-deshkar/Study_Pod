from django import forms
from django.utils import timezone

from .models import Class, TeachingAssignment


class AttendanceSelectionForm(forms.Form):
    student_class = forms.ModelChoiceField(
        queryset=Class.objects.none(),
        label="Class",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"},
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    def __init__(self, *args, teacher, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student_class"].queryset = Class.objects.filter(
            teaching_assignments__teacher=teacher
        ).distinct().order_by("name", "section")

