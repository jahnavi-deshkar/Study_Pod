from academics.models import Notice, Class
from django import forms
from .models import User, TeacherProfile, StudentProfile, ParentProfile


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-control"
            })


class TeacherProfileForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ["department"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-control"
            })


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = []


class ParentProfileForm(forms.ModelForm):
    class Meta:
        model = ParentProfile
        fields = ["phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-control"
            })
class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ["title", "content", "student_class", "attachment"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Notice title"
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Write your notice here..."
                }
            ),
            "student_class": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),
            "attachment": forms.ClearableFileInput(
                attrs={
                    "class": "form-control"
                }
            ),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)

        if teacher:
            self.fields["student_class"].queryset = Class.objects.filter(
                teaching_assignments__teacher=teacher
            ).distinct()
class AttendanceForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control"
            }
        )
    )

    student_class = forms.ModelChoiceField(
        queryset=Class.objects.all(),
        widget=forms.Select(
            attrs={"class": "form-select"}
        )
    )

