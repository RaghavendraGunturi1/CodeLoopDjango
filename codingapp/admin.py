from django.contrib import admin
from django import forms
from django.forms import formset_factory
from .models import Module, Question, Submission
from .models import Assessment, AssessmentQuestion, AssessmentSubmission

# ==================== Custom Forms for Question Test Cases ====================

DEFAULT_TEST_CASE_INPUT = "Enter input here"
DEFAULT_TEST_CASE_OUTPUT = "Enter expected output here"

class TestCaseForm(forms.Form):
    input = forms.CharField(
        max_length=200,
        required=False,
        initial=DEFAULT_TEST_CASE_INPUT,
        widget=forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        help_text="Enter the input for this test case (leave blank if no input is needed)."
    )
    expected_output = forms.CharField(
        max_length=200,
        required=True,
        initial=DEFAULT_TEST_CASE_OUTPUT,
        widget=forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        help_text="Enter the expected output for this test case."
    )

TestCaseFormSet = formset_factory(TestCaseForm, extra=2, can_delete=True)

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['test_cases'].widget = forms.HiddenInput()

        initial_test_cases = []
        if self.instance.pk:
            try:
                initial_test_cases = self.instance.test_cases or []
                if not isinstance(initial_test_cases, list):
                    import json
                    initial_test_cases = json.loads(self.instance.test_cases) if self.instance.test_cases else []
            except (ValueError, TypeError):
                initial_test_cases = [{"input": DEFAULT_TEST_CASE_INPUT, "expected_output": DEFAULT_TEST_CASE_OUTPUT}]
        else:
            initial_test_cases = [
                {"input": DEFAULT_TEST_CASE_INPUT, "expected_output": DEFAULT_TEST_CASE_OUTPUT},
                {"input": DEFAULT_TEST_CASE_INPUT, "expected_output": DEFAULT_TEST_CASE_OUTPUT},
            ]
        prefix = self.prefix + '-test_cases' if self.prefix else f"question_form-{self.instance.pk}-test_cases" if self.instance.pk else 'test_cases'
        self.test_case_formset = TestCaseFormSet(
            data=self.data if self.is_bound else None,
            initial=[{'input': tc.get('input', DEFAULT_TEST_CASE_INPUT), 'expected_output': tc.get('expected_output', DEFAULT_TEST_CASE_OUTPUT)} for tc in initial_test_cases],
            prefix=prefix
        )

    def is_valid(self):
        return super().is_valid() and self.test_case_formset.is_valid()

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.test_case_formset.is_valid():
            test_cases_data = [
                {"input": form.cleaned_data.get('input', ''), "expected_output": form.cleaned_data['expected_output']}
                for form in self.test_case_formset.forms
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False)
            ]
            instance.test_cases = test_cases_data
        if commit:
            instance.save()
        return instance

# ==================== Admin Interfaces ====================

class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1
    readonly_fields = ('module',)

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    change_form_template = 'admin/codingapp/module/change_form.html'
    list_display = ('title',)
    search_fields = ('title',)
    inlines = [QuestionInline]

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionForm
    change_form_template = 'admin/codingapp/question/change_form.html'
    list_display = ('title', 'module')
    search_fields = ('title',)
    list_filter = ('module',)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        form_class = self.form
        form = form_class(request.POST or None, instance=obj, prefix=f'question_form-{object_id}')
        if hasattr(form, 'test_case_formset'):
            extra_context['test_case_formset'] = form.test_case_formset
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        form = self.form()
        if hasattr(form, 'test_case_formset'):
            extra_context['test_case_formset'] = form.test_case_formset
        return super().add_view(request, form_url, extra_context=extra_context)

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'question', 'status', 'submitted_at')
    search_fields = ('user__username', 'question__title')
    list_filter = ('status', 'language', 'submitted_at')

# ==================== Assessment Admin Setup ====================

class AssessmentQuestionInline(admin.TabularInline):
    model = AssessmentQuestion
    extra = 1

@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "start_time", "end_time", "duration_minutes")
    inlines = [AssessmentQuestionInline]
    search_fields = ("title",)
    list_filter = ("start_time", "end_time")

@admin.register(AssessmentSubmission)
class AssessmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "assessment", "question", "score", "submitted_at")
    list_filter = ("assessment", "score", "submitted_at")
    search_fields = ("user__username", "assessment__title", "question__title")

@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'question')

from django.contrib import admin
from .models import Group

class GroupAdmin(admin.ModelAdmin):
    list_display = ('name',)  # Add more fields if you want
    filter_horizontal = ('students',)  # Makes the student selection easier

admin.site.register(Group, GroupAdmin)


from django.contrib import admin
from .models import Course, CourseContent

class CourseContentInline(admin.TabularInline):
    model = CourseContent
    extra = 1

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'difficulty', 'is_public', 'created_by')
    inlines = [CourseContentInline]
    filter_horizontal = ('groups',)
