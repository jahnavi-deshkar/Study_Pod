from django import forms
from pathlib import PurePath
from django.utils import timezone

from accounts.models import StudentProfile

from .models import Class, DoubtReply, DoubtThread, Subject, TeachingAssignment


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(item, initial) for item in files]


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
    PRIVACY_CHOICES = (
        ("PRIVATE", "Private — only you and your assigned teacher can see this"),
        ("PUBLIC", "Public — share anonymously with classmates"),
    )
    MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
    ALLOWED_ATTACHMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

    privacy = forms.ChoiceField(
        choices=PRIVACY_CHOICES,
        initial="PRIVATE",
        required=False,
        widget=forms.RadioSelect,
        label="Privacy",
    )
    attachments = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={
            "multiple": True,
            "accept": ".png,.jpg,.jpeg,.pdf",
            "class": "form-control",
        }),
        label="Attachments",
        help_text="PNG, JPG, JPEG, or PDF. Maximum 10 MB per file.",
    )

    class Meta:
        model = DoubtThread
        fields = ("subject", "category", "title", "content", "document_link")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Question title", "required": True}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Describe your question", "required": True}),
            "subject": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select", "required": True}),
            "document_link": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
        }

    def __init__(self, *args, student_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.none()
        if student_class is not None:
            self.fields["subject"].queryset = Subject.objects.filter(
                teaching_assignments__student_class=student_class
            ).distinct().order_by("name")
        self.fields["category"].label = "Doubt category"
        self.fields["category"].initial = ""
        self.fields["document_link"].label = "Document link (optional)"

    def clean_attachments(self):
        uploaded = self.cleaned_data.get("attachments", [])
        for item in uploaded:
            extension = PurePath(item.name).suffix.lower()
            if extension not in self.ALLOWED_ATTACHMENT_EXTENSIONS:
                raise forms.ValidationError("Attach only PNG, JPG, JPEG, or PDF files.")
            if item.size > self.MAX_ATTACHMENT_SIZE:
                raise forms.ValidationError("Each attachment must be 10 MB or smaller.")
        return uploaded


class DoubtReplyForm(forms.ModelForm):
    attachments = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={
            "multiple": True,
            "accept": ".png,.jpg,.jpeg,.pdf",
            "class": "form-control",
        }),
        label="Attach files",
        help_text="PNG, JPG, JPEG, or PDF. Maximum 10 MB per file.",
    )

    class Meta:
        model = DoubtReply
        fields = ("content",)
        widgets = {
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Write a reply"}),
        }

    def clean_attachments(self):
        uploaded = self.cleaned_data.get("attachments", [])
        for item in uploaded:
            extension = PurePath(item.name).suffix.lower()
            if extension not in DoubtThreadForm.ALLOWED_ATTACHMENT_EXTENSIONS:
                raise forms.ValidationError("Attach only PNG, JPG, JPEG, or PDF files.")
            if item.size > DoubtThreadForm.MAX_ATTACHMENT_SIZE:
                raise forms.ValidationError("Each attachment must be 10 MB or smaller.")
        return uploaded


class DoubtStudentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, student):
        name = student.user.get_full_name() or student.user.username
        username = f"@{student.user.username}"
        return f"{name} · {student.student_class} · {username}"


class DoubtInboxFilterForm(forms.Form):
    category = forms.ChoiceField(
        choices=[("", "All categories"), *DoubtThread.Category.choices],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Doubt category",
    )
    student_class = forms.ModelChoiceField(
        queryset=Class.objects.none(), required=False, empty_label="All assigned classes",
        widget=forms.Select(attrs={"class": "form-select"}), label="Class / Batch",
    )
    student = DoubtStudentChoiceField(
        queryset=StudentProfile.objects.none(), required=False, empty_label="All students",
        widget=forms.Select(attrs={"class": "form-select", "id": "studentFilter"}),
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(), required=False, empty_label="All subjects",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date_range = forms.ChoiceField(
        choices=[("ALL", "Any date"), ("TODAY", "Today"), ("LAST_7_DAYS", "Last 7 days"), ("CUSTOM", "Custom range")],
        required=False, initial="ALL", widget=forms.Select(attrs={"class": "form-select", "id": "dateRangeFilter"}),
        label="Submission date",
    )
    start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="From",
    )
    end_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="To",
    )
    status = forms.ChoiceField(
        choices=[("ALL", "All statuses"), *DoubtThread.Status.choices], required=False,
        initial="ALL", widget=forms.Select(attrs={"class": "form-select"}),
    )
    q = forms.CharField(
        required=False, label="Search doubts",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Title or description"}),
    )

    def __init__(self, *args, teacher, **kwargs):
        super().__init__(*args, **kwargs)
        assignments = TeachingAssignment.objects.filter(teacher=teacher)
        class_ids = assignments.values_list("student_class_id", flat=True)
        self.fields["student_class"].queryset = Class.objects.filter(pk__in=class_ids).order_by("name", "section")
        self.fields["subject"].queryset = Subject.objects.filter(
            teaching_assignments__teacher=teacher
        ).distinct().order_by("name")
        self.fields["student"].queryset = StudentProfile.objects.filter(
            student_class__in=self.fields["student_class"].queryset
        ).select_related("user", "student_class").order_by("user__last_name", "user__first_name", "user__username")

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error("end_date", "End date must be on or after the start date.")
        if cleaned_data.get("date_range") == "CUSTOM" and not (start_date or end_date):
            self.add_error("start_date", "Enter a start date, end date, or both for a custom range.")
        return cleaned_data

