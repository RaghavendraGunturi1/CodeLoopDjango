from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils import timezone

# ---- Helper for test case structure ----
def validate_test_cases(value):
    if not isinstance(value, list):
        raise ValidationError("Test cases must be a list.")
    for test in value:
        if not isinstance(test, dict) or "input" not in test or "expected_output" not in test:
            raise ValidationError("Each test case must be a dict with 'input' and 'expected_output' keys.")
        if not isinstance(test["input"], str):
            raise ValidationError("The 'input' field must be a string.")
        if not isinstance(test["expected_output"], list):
            raise ValidationError("The 'expected_output' field must be a list.")
        if not all(isinstance(line, str) for line in test["expected_output"]):
            raise ValidationError("All elements in 'expected_output' must be strings.")

# ---- Group model ----
class Group(models.Model):
    name = models.CharField(max_length=100, unique=True)
    students = models.ManyToManyField(User, related_name='custom_groups')

    def __str__(self):
        return self.name

# ---- Module model ----
class Module(models.Model):
    title = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    groups = models.ManyToManyField(Group, related_name='modules', blank=True)  # Only here!

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['title']

# ---- Question model ----
class Question(models.Model):
    QUESTION_TYPES = [
        ('coding', 'Coding Problem'),
        ('mcq', 'Multiple Choice'),
    ]
    question_type = models.CharField(
        max_length=20, choices=QUESTION_TYPES, default='coding'
    )
    options = models.JSONField(blank=True, null=True, help_text="For MCQs: List of options")
    correct_answer = models.CharField(max_length=200, blank=True, help_text="For MCQs: Correct option text")
    title = models.CharField(max_length=200)
    description = models.TextField()
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="questions", null=True, blank=True)
    test_cases = models.JSONField(
        default=list,
        validators=[validate_test_cases],
        help_text="List of dicts with 'input' (string) and 'expected_output' (list of strings). Example: [{'input': '2', 'expected_output': ['2 2 2', '2 1 2', '2 2 2']}]"
    )

    def __str__(self):
        return self.title

    class Meta:
        unique_together = ['module', 'title']

# ---- Language Choices ----
SUPPORTED_LANGUAGES = ["python", "c", "cpp", "java", "javascript"]
LANGUAGE_CHOICES = [(lang, lang.capitalize()) for lang in SUPPORTED_LANGUAGES]

# ---- Submission model (Practice Section) ----
class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending", "Pending"
        ACCEPTED = "Accepted", "Accepted"
        REJECTED = "Rejected", "Rejected"

    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.TextField(blank=True)
    language = models.CharField(max_length=50, choices=LANGUAGE_CHOICES, default="python")
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    output = models.TextField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.question.title} ({self.submitted_at})"

    class Meta:
        ordering = ['-submitted_at']

# -----------------------------
# 🔥 Assessment Feature Models
# -----------------------------

class Assessment(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    quiz = models.ForeignKey('Quiz', on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments')
    duration_minutes = models.PositiveIntegerField(help_text="Duration in minutes")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    groups = models.ManyToManyField(Group, related_name='assessments', blank=True)  # Only here!

    def __str__(self):
        return self.title

    def is_active(self):
        now = timezone.now()
        return self.start_time <= now <= self.end_time

class AssessmentQuestion(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['assessment', 'question']

    def __str__(self):
        return f"{self.assessment.title} - {self.question.title}"

class AssessmentSubmission(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.TextField()
    language = models.CharField(max_length=30)
    submitted_at = models.DateTimeField(auto_now_add=True)
    score = models.IntegerField(default=0)
    output = models.TextField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ['assessment', 'question', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.assessment.title} - {self.question.title}"

class AssessmentSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    start_time = models.DateTimeField(null=True, blank=True)
    quiz_submitted = models.BooleanField(default=False)

    class Meta:
        unique_together = ['user', 'assessment']

# ---- UserProfile model ----
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    full_name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.full_name or self.user.username
    
from django.db import models
from django.contrib.auth.models import User

class Quiz(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    questions = models.ManyToManyField('Question', limit_choices_to={'question_type': 'mcq'})
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class QuizSubmission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    submitted_at = models.DateTimeField(auto_now_add=True)
    score = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} - {self.score}"

class QuizAnswer(models.Model):
    submission = models.ForeignKey(QuizSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.submission.user.username} - {self.question.title}"

from codingapp.models import Group  
class Note(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='notes/')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)

from django.db import models
from django.contrib.auth.models import User

class Notice(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey('Group', on_delete=models.SET_NULL, null=True, blank=True)
    for_everyone = models.BooleanField(default=False)
    attachment = models.FileField(upload_to='notices/', blank=True, null=True)

    def __str__(self):
        return self.title

class NoticeReadStatus(models.Model):
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('notice', 'user')


from django.db import models
from django.contrib.auth.models import User

class Course(models.Model):
    DIFFICULTY_CHOICES = [
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Advanced', 'Advanced'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)
    prerequisites = models.TextField(blank=True)
    time_to_complete = models.DurationField(help_text="e.g. 01:30:00 for 1.5 hours")
    is_public = models.BooleanField(default=False)
    groups = models.ManyToManyField("Group", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class CourseContent(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="contents")
    title = models.CharField(max_length=255)
    video_url = models.URLField(blank=True, null=True)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"

# models.py

class StudentPerformance(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, null=True, blank=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    attempts = models.PositiveIntegerField(default=0)
    last_submitted = models.DateTimeField(auto_now=True)
    is_correct = models.BooleanField(default=False)


class ModuleCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    manually_marked = models.BooleanField(default=False)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'module')

# in models.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
