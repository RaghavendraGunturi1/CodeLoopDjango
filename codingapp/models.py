# codingapp/models.py
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.utils import OperationalError, ProgrammingError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()

# -----------------------------
# RBAC models
# -----------------------------
class ActionPermission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name or self.code

    class Meta:
        verbose_name = "Action Permission"
        verbose_name_plural = "Action Permissions"


class Role(models.Model):
    """
    User roles such as Admin, HOD, Teacher, Student.
    Each role has a set of default permissions.
    """
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    permissions = models.ManyToManyField(
        ActionPermission, blank=True, related_name="roles"
    )

    def __str__(self):
        return self.name


class Department(models.Model):
    """
    Academic departments managed by a Head of Department.
    """
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True)
    # Will link to a UserProfile once the HOD is assigned
    hod = models.OneToOneField(
        'UserProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_department'
    )

    def __str__(self):
        return self.name


# -----------------------------
# Helpers and validation
# -----------------------------
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


# -----------------------------
# Domain models
# -----------------------------
# --- Group model ---
class Group(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(
        'Department',
        on_delete=models.CASCADE,
        related_name='groups',
        null=True,
        blank=True
    )
    students = models.ManyToManyField(User, related_name='custom_groups', blank=True)

    class Meta:
        unique_together = ('name', 'department')
        ordering = ['department__name', 'name']

    def __str__(self):
        if self.department:
            return f"{self.name} ({self.department.name})"
        return self.name



class Module(models.Model):
    title = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    groups = models.ManyToManyField(Group, related_name='modules', blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['title']


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
        help_text="List of dicts with 'input' and 'expected_output' keys."
    )

    def __str__(self):
        return self.title

    class Meta:
        unique_together = ['module', 'title']


SUPPORTED_LANGUAGES = ["python", "c", "cpp", "java", "javascript"]
LANGUAGE_CHOICES = [(lang, lang.capitalize()) for lang in SUPPORTED_LANGUAGES]


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
# Assessment models
# -----------------------------
class Assessment(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    quiz = models.ForeignKey('Quiz', on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments')
    duration_minutes = models.PositiveIntegerField(help_text="Duration in minutes")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    groups = models.ManyToManyField(Group, related_name='assessments', blank=True)

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
    end_time = models.DateTimeField(null=True, blank=True)
    quiz_submitted = models.BooleanField(default=False)

    class Meta:
        unique_together = ['user', 'assessment']


# -----------------------------
# User profile and RBAC fields
# -----------------------------
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True,
        default='profiles/default_profile.png'
    )
    full_name = models.CharField(max_length=100, blank=True)

    # RBAC
    role = models.ForeignKey('Role', on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True)
    custom_permissions = models.ManyToManyField('ActionPermission', blank=True, related_name='users_with_custom_permissions')

    def __str__(self):
        return self.full_name or self.user.username

    # Helper methods for permission aggregation
    def get_role_permissions(self):
        if self.role:
            return set(self.role.permissions.all())
        return set()

    def get_user_permissions(self):
        return set(self.custom_permissions.all())

    def get_all_permissions(self):
        # Return set of permission codes (role + custom)
        return {p.code for p in (self.get_role_permissions() | self.get_user_permissions())}

    def permission_codes(self):
        """
        Return a set of permission codes (strings) that this user effectively has:
        union of role permissions and custom permissions.
        """
        # role permissions (codes)
        role_codes = set()
        if self.role:
            role_codes = set(self.role.permissions.values_list("code", flat=True))
        custom_codes = set(self.custom_permissions.values_list("code", flat=True))
        return role_codes | custom_codes

    def has_permission(self, code):
        """
        Convenience check whether user has the given permission code.
        """
        return code in self.permission_codes()


# -----------------------------
# Quiz models
# -----------------------------
class Quiz(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    questions = models.ManyToManyField('Question', limit_choices_to={'question_type': 'mcq'}, blank=True)
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


# -----------------------------
# Notes, Notices, Courses
# -----------------------------
class Note(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='notes/')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)


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


# -----------------------------
# Student performance & module completion
# -----------------------------
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


# -----------------------------
# Signals
# -----------------------------
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        profile, created_flag = UserProfile.objects.get_or_create(user=instance)
        if created_flag:
            # ensure a default profile picture path is present
            profile.profile_picture = profile.profile_picture or 'profiles/default_profile.png'
            profile.save()


# -----------------------------
# Permission registry & defaults
# -----------------------------
# Base/default permissions (merged from previous list + view-derived perms)
DEFAULT_PERMISSIONS = [
    # System / General
    ("view_dashboard", "View Dashboard", "Access the main dashboard"),
    ("view_profile", "View Profile", "View own profile and info"),
    ("edit_profile", "Edit Profile", "Update profile details"),
    ("change_password", "Change Password", "Change user password"),
    ("view_leaderboard", "View Leaderboard", "Access leaderboard"),

    # User & Role Management
    ("manage_users", "Manage Users", "Create, update, or deactivate users"),
    ("bulk_edit_users", "Bulk Edit Users", "Edit multiple users at once"),
    ("assign_roles", "Assign Roles", "Assign roles to users"),
    ("view_user_list", "View User List", "See all users"),
    ("view_user_detail", "View User Detail", "View individual user info"),
    ("delete_user", "Delete User", "Delete or disable users"),
    ("manage_departments", "Manage Departments", "Create/edit departments"),
    ("assign_hod", "Assign HODs", "Assign Head of Department"),
    ("manage_roles_permissions", "Manage Roles & Permissions", "Manage role-based permissions"),
    ("manage_permissions", "Manage Permissions", "Manage permission mappings"),

    # Department / HOD Controls
    ("view_department", "View Department", "Access department dashboard"),
    ("manage_teachers", "Manage Teachers", "Edit or remove teachers"),
    ("manage_students", "Manage Students", "Edit or remove students"),
    ("view_hod_dashboard", "View HOD Dashboard", "Access the HOD dashboard"),
    ("hod_assign_permissions", "HOD Assign Permissions", "Allow HODs to grant permissions"),
    ("assign_teacher", "Assign Teachers", "Assign teachers to classes or courses"),
    ("assign_student", "Assign Students", "Assign students to classes or courses"),
    ("manage_groups", "Manage Groups", "Create or delete groups (classes/sections)"),

    # Modules
    ("view_modules", "View Modules", "View list of modules"),
    ("view_module_detail", "View Module Details", "Open module detail"),
    ("add_module", "Add Module", "Create a new module"),
    ("edit_module", "Edit Module", "Edit existing module"),
    ("delete_module", "Delete Module", "Remove a module"),
    ("mark_module_completed", "Mark Module Completed", "Mark module as completed for a user"),
    ("add_question_to_module", "Add Question to Module", "Attach question to module"),

    # Questions
    ("view_questions", "View Questions", "View list of questions"),
    ("view_question_detail", "View Question Details", "View question detail"),
    ("add_question", "Add Question", "Create question"),
    ("edit_question", "Edit Question", "Edit question"),
    ("delete_question", "Delete Question", "Delete question"),
    ("execute_code", "Execute Code", "Run code in sandbox"),
    ("teacher_bulk_upload_mcq", "Bulk Upload MCQ (Teacher)", "Teacher MCQ bulk upload"),
    ("bulk_mcq_upload", "Bulk Upload MCQ (Admin)", "Admin MCQ bulk upload"),

    # Assessments & Quizzes
    ("view_assessments", "View Assessments", "View assessments list"),
    ("view_assessment_detail", "View Assessment Detail", "View assessment details"),
    ("attempt_assessment_quiz", "Attempt Assessment Quiz", "Student attempt assessment quiz"),
    ("attempt_assessment_code", "Attempt Assessment Code", "Student attempt coding assessment"),
    ("view_assessment_leaderboard", "View Assessment Leaderboard", "View assessment leaderboard"),
    ("export_assessment_leaderboard", "Export Assessment Leaderboard", "Export leaderboard"),
    ("reset_assessment_submissions", "Reset Assessment Submissions", "Reset submissions for assessment"),
    ("assessment_result", "View Assessment Result", "View individual assessment result"),
    ("take_quiz", "Take Quiz", "Student take quiz"),
    ("view_quiz_result", "View Quiz Result", "View quiz result"),
    ("view_quiz_leaderboard", "View Quiz Leaderboard", "View quiz leaderboard"),
    ("create_quiz", "Create Quiz", "Create new quizzes"),
    ("edit_quiz", "Edit Quiz", "Modify existing quizzes"),
    ("delete_quiz", "Delete Quiz", "Delete quizzes"),
    ("view_quiz", "View Quiz", "View quiz details"),
    ("assign_quiz", "Assign Quiz", "Assign quizzes to students"),
    ("submit_quiz", "Submit Quiz", "Allow students to submit quizzes"),
    ("grade_quiz", "Grade Quiz", "Evaluate and assign grades"),
    ("view_results", "View Results", "View quiz results"),
    ("reset_quiz_attempt", "Reset Quiz Attempt", "Reset quiz submissions"),

    # Notes / Materials
    ("upload_notes", "Upload Notes", "Upload study materials"),
    ("edit_notes", "Edit Notes", "Modify uploaded notes"),
    ("delete_notes", "Delete Notes", "Remove notes"),
    ("view_notes", "View Notes", "Access uploaded notes"),
    ("share_notes", "Share Notes", "Share notes with others"),
    ("view_uploaded_notes", "View Uploaded Notes", "View available notes"),

    # Notices / Announcements
    ("view_notices", "View Announcements", "View announcements"),
    ("add_notice", "Add Announcement", "Create an announcement"),
    ("edit_notice", "Edit Announcement", "Edit announcement"),
    ("delete_notice", "Delete Announcement", "Delete announcement"),
    ("view_announcements", "View Announcements (alias)", "View announcements"),  # alias / compatibility

    # Courses & Content
    ("create_course", "Create Course", "Create courses"),
    ("edit_course", "Edit Course", "Edit courses"),
    ("delete_course", "Delete Course", "Delete courses"),
    ("manage_courses", "Manage Courses", "Course management"),
    ("view_course_content", "View Course Content", "View content"),
    ("manage_course_content", "Manage Course Content", "Manage content"),

    # Teacher-specific
    ("teacher_dashboard", "Access Teacher Dashboard", "Teacher dashboard"),
    ("teacher_manage_modules", "Manage Modules (Teacher)", "Teacher module management"),
    ("teacher_manage_questions", "Manage Questions (Teacher)", "Teacher question management"),
    ("teacher_manage_assessments", "Manage Assessments (Teacher)", "Teacher assessment management"),
    ("teacher_manage_groups", "Manage Groups (Teacher)", "Teacher group management"),
    ("teacher_manage_quizzes", "Manage Quizzes (Teacher)", "Teacher quiz management"),
    ("teacher_manage_courses", "Manage Courses (Teacher)", "Teacher course management"),
    ("manage_groups", "Manage Groups", "Create or delete groups (classes/sections)"),

    # Analytics / Performance
    ("view_student_performance", "View Student Performance", "View student analytics"),
    ("view_student_detail", "View Student Detail", "View student details"),
    ("export_student_performance", "Export Student Performance", "Export performance data"),

    # System / Admin
    ("access_admin_panel", "Access Admin Panel", "Access the Admin Control Center"),
    ("system_configuration", "System Configuration", "Change platform settings"),
    ("system_settings", "System Settings", "Edit system settings"),
    ("view_audit_logs", "View Audit Logs", "View recent user actions"),
    ("backup_database", "Backup Database", "Create database backups"),
    ("restore_database", "Restore Database", "Restore database backups"),
    ("delete_anything", "Delete Any Object", "Delete any record (superuser only)"),

    # Misc / API-like
    ("run_code", "Run Code API", "Run code in sandbox"),
    ("clear_splash_flag", "Clear Splash Flag", "Clear splash screen"),
    ("check_submission_status", "Check Submission Status", "Check submission status endpoint"),
]


def ensure_default_permissions():
    """Ensure all default permissions exist in the DB."""
    try:
        for code, name, desc in DEFAULT_PERMISSIONS:
            ActionPermission.objects.get_or_create(
                code=code,
                defaults={"name": name, "description": desc},
            )
    except (OperationalError, ProgrammingError):
        # Database not ready (e.g., during migrate)
        pass


# ===========================================================
# Default role permission mapping
# ===========================================================
ROLE_DEFAULT_PERMISSIONS = {
    "admin": ["*"],

    "hod": [
        # General
        "view_dashboard", "view_profile", "edit_profile", "view_leaderboard", "view_notices", "view_announcements",
        "add_notice", "edit_notice", "delete_notice",

        # Users / Departments / Roles
        "manage_departments", "manage_teachers", "manage_students", "manage_users", "bulk_edit_users",
        "assign_roles", "assign_hod", "manage_roles_permissions", "manage_permissions", "hod_assign_permissions",

        # Modules & Questions
        "view_modules", "view_module_detail", "add_module", "edit_module", "delete_module",
        "add_question_to_module", "view_questions", "add_question", "edit_question", "delete_question",

        # Assessments & Quizzes
        "view_assessments", "view_assessment_detail", "create_quiz", "edit_quiz", "delete_quiz", "view_quiz",
        "assign_quiz", "grade_quiz", "view_results", "view_quiz_leaderboard", "reset_assessment_submissions",
        "export_assessment_leaderboard", "assessment_result",

        # Notes & Content
        "upload_notes", "edit_notes", "delete_notes", "view_notes", "view_uploaded_notes",

        # Analytics
        "view_student_performance", "view_student_detail", "export_student_performance",
    ],

    "teacher": [
        "view_dashboard", "view_profile", "edit_profile", "view_leaderboard", "view_notices",
        # Modules / Questions
        "view_modules", "view_module_detail", "add_module", "edit_module", "delete_module",
        "view_questions", "add_question", "edit_question", "delete_question", "teacher_bulk_upload_mcq", "execute_code",
        # Assessments / Quizzes
        "teacher_manage_assessments", "teacher_manage_quizzes", "view_assessments", "view_assessment_detail",
        "take_quiz", "view_quiz_result", "view_quiz_leaderboard", "assessment_result", "reset_assessment_submissions",
        "view_results",
        # Notes
        "upload_notes", "edit_notes", "delete_notes", "view_notes",
    ],

    "student": [
        "view_dashboard", "view_profile", "edit_profile",
        "view_modules", "view_module_detail",
        "view_questions", "view_question_detail",
        "execute_code",
        "take_quiz", "attempt_assessment_quiz", "attempt_assessment_code",
        "view_quiz_result", "view_assessment_leaderboard", "assessment_result",
        "view_notes", "view_notices", "view_uploaded_notes", "post_feedback",
    ],
}


def assign_default_permissions_to_roles():
    """
    Assign predefined permissions to each system role.
    Admin gets all permissions.
    """
    try:
        all_codes = set(ActionPermission.objects.values_list("code", flat=True))
        for role_name, perm_codes in ROLE_DEFAULT_PERMISSIONS.items():
            role, _ = Role.objects.get_or_create(name=role_name)
            if "*" in perm_codes:
                perms = ActionPermission.objects.all()
                role.permissions.set(perms)
                print(f"✅ Assigned ALL permissions to '{role_name}'")
            else:
                missing = [c for c in perm_codes if c not in all_codes]
                if missing:
                    print(f"⚠️ Missing permutations for {role_name}: {missing}")
                perms = ActionPermission.objects.filter(code__in=perm_codes)
                role.permissions.set(perms)
                print(f"✅ Assigned {perms.count()} permissions to '{role_name}'")
            role.save()
    except (OperationalError, ProgrammingError):
        pass
