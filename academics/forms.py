from django import forms
from django.utils import timezone

from .models import Class, DoubtReply, DoubtThread, Subject, TeachingAssignment


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


class DoubtThreadForm(forms.ModelForm):
    class Meta:
        model = DoubtThread
        fields = ("subject", "title", "content")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Question title"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Describe your question"}),
            "subject": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, student_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.none()
        if student_class is not None:
            self.fields["subject"].queryset = Subject.objects.filter(
                teaching_assignments__student_class=student_class
            ).distinct().order_by("name")


class DoubtReplyForm(forms.ModelForm):
    class Meta:
        model = DoubtReply
        fields = ("content",)
        widgets = {
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Write a reply"}),
        }

