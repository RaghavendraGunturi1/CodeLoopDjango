# codingapp/forms.py
from django import forms
from .models import Module, Question
import json

from .models import Module, Question, Group # Ensure Module and Group are imported
class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["title", "description", "is_public", "groups"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "groups": forms.CheckboxSelectMultiple(),  # ✅ FIXED
        }


from django.forms import formset_factory

class TestCaseForm(forms.Form):
    input = forms.CharField(
        label="Test Case Input",
        widget=forms.Textarea(attrs={'rows': 1, 'class': 'form-control'}),
        required=True,
    )
    expected_output = forms.CharField(
        label="Expected Output (one per line)",
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        required=True,
        help_text="Each line will be one expected output for this test case."
    )

TestCaseFormSet = formset_factory(TestCaseForm, extra=1, can_delete=True)


import json
from django import forms
from .models import Question

class QuestionForm(forms.ModelForm):
    options = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": '["Option A", "Option B", "Option C", "Option D"]',
        }),
        help_text="Enter options as a JSON list (for MCQ questions).",
        required=False,
    )
    correct_answer = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Enter the correct option exactly as it appears above (for MCQ questions).",
        required=False,
    )

    class Meta:
        model = Question
        fields = ['title', 'description', 'module', 'question_type', 'options', 'correct_answer']
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "module": forms.Select(attrs={"class": "form-control"}),
            "question_type": forms.Select(attrs={"class": "form-control"}),
        }

    def clean_options(self):
        data = self.cleaned_data.get('options', '').strip()
        if not data:
            return []
        try:
            options = json.loads(data)
            if not isinstance(options, list):
                raise forms.ValidationError("Options must be a JSON list.")
            return options
        except json.JSONDecodeError:
            raise forms.ValidationError("Invalid JSON format for options.")

    def clean(self):
        cleaned_data = super().clean()
        question_type = cleaned_data.get('question_type')
        if question_type == 'mcq':
            options = cleaned_data.get('options')
            correct_answer = cleaned_data.get('correct_answer')
            if not options or not correct_answer:
                raise forms.ValidationError("For MCQs, both options and correct answer are required.")
            if correct_answer not in options:
                raise forms.ValidationError("Correct answer must match one of the options.")
        # No test_cases validation here; handled by formset in the view!
        return cleaned_data


# forms.py
from .models import Assessment

from django import forms
from .models import Quiz, Question

from django import forms
from .models import Quiz, Question

class QuizForm(forms.ModelForm):
    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.filter(question_type='mcq'),
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 15}),
        required=False,   # 👈 MAKE OPTIONAL
        help_text="Hold Ctrl (Windows) or Cmd (Mac) to select multiple questions."
    )

    class Meta:
        model = Quiz
        fields = ['title', 'description', 'questions']

class AssessmentForm(forms.ModelForm):
    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 15}),
        required=False,
        help_text="Hold Ctrl (Windows) or Cmd (Mac) to select multiple questions."
    )

    class Meta:
        model = Assessment
        fields = ['title', 'description', 'start_time', 'end_time', 'duration_minutes', 'groups', 'quiz', 'questions']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'groups': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'quiz': forms.Select(attrs={'class': 'form-control'}),
            'questions': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }




from django import forms
from .models import Group

class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'students']  # Only use fields that exist on Group
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "students": forms.SelectMultiple(attrs={"class": "form-control"}),
        }


from django import forms

class ExcelUploadForm(forms.Form):
    file = forms.FileField(label="Select Excel File (.xlsx)")


from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

# codingapp/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
import re
from .models import Group, Department

# codingapp/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
import re
from .models import Group, Department

class RegistrationForm(UserCreationForm):
    ROLE_CHOICES = (
        ("student", "Student"),
        ("teacher", "Teacher"),
    )

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    email = forms.EmailField(required=True)

    # used for both:
    # student → roll number
    # teacher → custom username
    username_input = forms.CharField(
        max_length=30,
        label="Roll Number / Username"
    )

    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=True
    )

    class Meta:
        model = User
        fields = (
            "username_input",
            "email",
            "password1",
            "password2",
            "role",
            "group",
            "department",
        )

    def clean_username_input(self):
        username = self.cleaned_data["username_input"]
        role = self.cleaned_data.get("role")

        if role == "student":
            # STRICT roll number rules
            if not re.fullmatch(r"[0-9]{2}[A-Z0-9]{4}[0-9]{2}[A-Z0-9]{2}", username):
                raise forms.ValidationError(
                    "Invalid roll number format. Example: 23AGCS0123"
                )
        else:
            # Teacher: allow anything except spaces
            if " " in username:
                raise forms.ValidationError(
                    "Username should not contain spaces"
                )

        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        role = self.cleaned_data.get("role")

        if role == "teacher" and not email.endswith("@aceec.ac.in"):
            raise forms.ValidationError(
                "Teachers must use an @aceec.ac.in email address"
            )

        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        group = cleaned.get("group")

        if role == "student" and not group:
            self.add_error("group", "Group is required for students")

        return cleaned



from django import forms
from django.contrib.auth.models import User
from codingapp.models import Group, Department
from codingapp.utils import validate_roll_number

from django import forms
from django.contrib.auth.models import User
from codingapp.models import Group, Department
import re

ROLL_REGEX = r"^[0-9]{2}[A-Z0-9]{4}[0-9]{2}[A-Z0-9]{2}$"

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from codingapp.models import Department, Group

ROLE_CHOICES = (
    ("student", "Student"),
    ("teacher", "Teacher"),
)

class StudentRegistrationForm(UserCreationForm):
    roll_number = forms.CharField(
        max_length=10,
        label="Roll Number",
        help_text="Example: 23AGCS0123"
    )

    email = forms.EmailField(required=True)

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        required=True,
        label="Register As"
    )

    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=True
    )

    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        help_text="Required only for students"
    )

    class Meta:
        model = User
        fields = (
            "roll_number",
            "email",
            "role",
            "department",
            "group",
            "password1",
            "password2",
        )

    # -------------------------------
    # Roll number validation
    # -------------------------------
    def clean_roll_number(self):
        roll = self.cleaned_data["roll_number"]

        if len(roll) != 10:
            raise forms.ValidationError("Roll number must be exactly 10 characters")

        if not roll.isalnum():
            raise forms.ValidationError("Only capital letters and numbers allowed")

        if not roll[:2].isdigit():
            raise forms.ValidationError("First 2 characters must be numbers")

        if not roll[2:6].isalnum():
            raise forms.ValidationError("Characters 3–6 must be alphanumeric")

        if not roll[6:8].isdigit():
            raise forms.ValidationError("Characters 7–8 must be numbers")

        if not roll[8:10].isalnum():
            raise forms.ValidationError("Characters 9–10 must be alphanumeric")

        return roll.upper()

    # -------------------------------
    # Cross-field validation
    # -------------------------------
    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        group = cleaned.get("group")

        if role == "student" and not group:
            self.add_error("group", "Students must select a group")

        if role == "teacher":
            cleaned["group"] = None  # teachers don't belong to student groups

        return cleaned


class TeacherRegistrationForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField(label="Official Email")
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)
    department = forms.ModelChoiceField(queryset=Department.objects.all())

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if not email.endswith("@aceec.ac.in"):
            raise forms.ValidationError("Teachers must use @aceec.ac.in email")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Passwords do not match")
        return cleaned


from django import forms
from .models import Note

class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['title', 'description', 'file', 'group']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].required = False
        self.fields['group'].label = "Visible To"
        self.fields['group'].empty_label = "Everyone"
    

from django import forms
from .models import Notice

class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ['title', 'content', 'group', 'for_everyone', 'attachment']


from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

class UserProfileEditForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['full_name', 'profile_picture']

class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['email']

from django import forms
from .models import Module

class BulkMCQUploadForm(forms.Form):
    module = forms.ModelChoiceField(queryset=Module.objects.all(), required=True, label="Module")
    file = forms.FileField(required=True, label="Excel File (.xlsx)")




from django import forms
from datetime import timedelta
import re

class DurationInputWidget(forms.TextInput):
    def __init__(self, attrs=None):
        default_attrs = {'placeholder': 'e.g. 1 day 2:30 or 2:15:00'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

class SmartDurationField(forms.Field):
    widget = DurationInputWidget

    def to_python(self, value):
        if not value:
            return None

        # Normalize input: handle "1 day 2:30", "2h 30m", etc.
        value = value.strip().lower()

        # Match patterns like "1 day 2:30" or "2:30" or "1:00:00"
        day_match = re.match(r'(?:(\d+)\s*days?\s*)?(\d+):(\d+)(?::(\d+))?', value)
        if day_match:
            days = int(day_match.group(1) or 0)
            hours = int(day_match.group(2) or 0)
            minutes = int(day_match.group(3) or 0)
            seconds = int(day_match.group(4) or 0)
            return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

        # Match simple formats like "2h 30m"
        short_match = re.findall(r'(\d+)\s*(h|hr|hour|m|min|minute|s|sec|second|d|day)', value)
        if short_match:
            time_data = {'days': 0, 'hours': 0, 'minutes': 0, 'seconds': 0}
            for amount, unit in short_match:
                amount = int(amount)
                if 'd' in unit:
                    time_data['days'] += amount
                elif 'h' in unit:
                    time_data['hours'] += amount
                elif 'm' in unit:
                    time_data['minutes'] += amount
                elif 's' in unit:
                    time_data['seconds'] += amount
            return timedelta(**time_data)

        raise forms.ValidationError("Enter duration like '1 day 2:30', '90m', or '2:15:00'.")


from django import forms
from .models import Course, CourseContent
from django.forms import inlineformset_factory

class CourseForm(forms.ModelForm):
    time_to_complete = SmartDurationField()
    class Meta:
        model = Course
        fields = ['title', 'description', 'difficulty', 'prerequisites', 'time_to_complete', 'is_public', 'groups']

from django import forms
from .models import CourseContent

class CourseContentForm(forms.ModelForm):
    class Meta:
        model = CourseContent
        exclude = ['course']  # ✅ completely disables this field

CourseContentFormSet = inlineformset_factory(
    Course,
    CourseContent,
    form=CourseContentForm,
    fields=['id', 'title', 'video_url', 'content', 'order'],  # ✅ keep as-is
    extra=1,
    can_delete=True
)



from django import forms

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        label="Registered Email",
        widget=forms.EmailInput(attrs={"class": "form-control"})
    )


class ResetPasswordForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("confirm_password"):
            raise forms.ValidationError("Passwords do not match")
        return cleaned


from django import forms
from codingapp.models import ExternalProfile

class ExternalProfileForm(forms.ModelForm):
    class Meta:
        model = ExternalProfile
        fields = [
            "codeforces_username",
            "leetcode_username",
            "codechef_username",
            "hackerrank_username",


        ]
        widgets = {
            "codeforces_username": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Codeforces username"}
            ),
            "leetcode_username": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "LeetCode username"}
            ),
            "codechef_username": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "CodeChef username"}
            ),
            "hackerrank_username": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "HackerRank username"}
            ),

        }
