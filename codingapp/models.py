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
    """
    Represents a class/section of students.
    - Created by HOD or Admin.
    - Can have multiple assigned teachers.
    - Teachers can view/edit only the groups assigned to them.
    """
    name = models.CharField(max_length=100)
    department = models.ForeignKey(
        'Department',
        on_delete=models.CASCADE,
        related_name='groups',
        null=True,
        blank=True
    )
    students = models.ManyToManyField(User, related_name='custom_groups', blank=True)
    teachers = models.ManyToManyField(
        User,
        related_name='teaching_groups',
        blank=True,
        help_text="Teachers assigned to manage this group"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='groups_created',
        help_text="The admin or HOD who created this group"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'department')
        ordering = ['department__name', 'name']

    def __str__(self):
        dept = f" ({self.department.name})" if self.department else ""
        return f"{self.name}{dept}"

    def can_user_manage(self, user):
        """Return True if user can view/edit this group."""
        profile = getattr(user, 'userprofile', None)
        if not profile or not profile.role:
            return False
        role = profile.role.name.lower()
        if role in ["admin", "hod"]:
            return True
        if role == "teacher":
            return self.teachers.filter(id=user.id).exists()
        return False



class Module(models.Model):
    title = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, null=True)

    # PUBLIC / GROUP ACCESS
    is_public = models.BooleanField(
        default=False,
        help_text="If checked, this module is visible to all students."
    )

    groups = models.ManyToManyField(
        Group,
        related_name="modules",
        blank=True,
        help_text="Assign this module to groups. Ignored if Is Public is enabled."
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


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
    plagiarism_percent = models.FloatField(default=0.0)
    output = models.TextField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)
    # Component signals (optional / nullable for backward compatibility)
    structural_similarity = models.FloatField(null=True, blank=True, help_text="AST/structural similarity (0.0-1.0)")
    token_similarity = models.FloatField(null=True, blank=True, help_text="Token/winnowing similarity (0.0-1.0)")
    embedding_similarity = models.FloatField(null=True, blank=True, help_text="Embedding cosine similarity (0.0-1.0)")
    ai_generated_prob = models.FloatField(null=True, blank=True, help_text="Estimated probability code is AI-generated (0.0-1.0)")
    # cache / diagnostic
    fingerprint = models.TextField(null=True, blank=True, help_text="Optional fingerprint or hash for quick comparisons")
    # inside AssessmentSubmission model
    raw_score = models.FloatField(null=True, blank=True, help_text="Raw marks before plagiarism penalty (0-5).")
    # If you want an updated timestamp:
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        unique_together = ['assessment', 'question', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.assessment.title} - {self.question.title}"


# in codingapp/models.py — modify AssessmentSession
class AssessmentSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    quiz_submitted = models.BooleanField(default=False)

    # NEW fields for cheat detection / heartbeat
    warnings_count = models.PositiveIntegerField(default=0)            # number of times fullscreen/visibility was violated
    last_heartbeat = models.DateTimeField(null=True, blank=True)       # last time we received a heartbeat
    flagged = models.BooleanField(default=False)                       # set True when auto-end enforced
    # models.py (AssessmentSession)
    penalty_percent = models.FloatField(default=0.0)
    penalty_factor = models.FloatField(default=1.0)
    raw_total = models.FloatField(null=True, blank=True)
    penalized_total = models.FloatField(null=True, blank=True)
    penalty_applied = models.BooleanField(default=False)

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


# ===========================================================
# 🧩 Unified Permission Registry (Final Version)
# ===========================================================

from django.db.utils import OperationalError, ProgrammingError


DEFAULT_PERMISSIONS = [
    # --- System / Account ---
    ("view_dashboard", "Access Main Dashboard", "View main dashboard and statistics"),
    ("view_profile", "View Profile", "View user profile"),
    ("edit_profile", "Edit Profile", "Edit personal profile"),
    ("change_password", "Change Password", "Change own password"),
    ("access_admin_panel", "Access Admin Control Center", "Access global admin tools"),
    ("manage_permissions", "Manage Permissions", "View and modify user permissions"),
    ("manage_roles_permissions", "Manage Role Permissions", "Manage which roles have which permissions"),
    ("manage_users", "Manage Users", "Add, edit, or delete users"),
    ("bulk_edit_users", "Bulk Edit Users", "Edit multiple users at once"),
    ("assign_roles", "Assign Roles", "Assign roles to users"),
    ("delete_user", "Delete User", "Remove a user permanently"),
    ("reset_passwords", "Reset Passwords", "Reset other users’ passwords"),
    ("backup_database", "Backup Database", "Export database backup"),
    ("restore_database", "Restore Database", "Restore database from backup"),
    ("view_audit_logs", "View Audit Logs", "View system activity logs"),
    ("system_configuration", "System Configuration", "Edit platform-wide settings"),

    # --- Departments / HOD / Groups ---
    ("manage_departments", "Manage Departments", "Create, update, delete departments"),
    ("view_department", "View Department", "Access a department dashboard"),
    ("assign_hod", "Assign HOD", "Assign Head of Department"),
    ("manage_teachers", "Manage Teachers", "Edit or remove teachers"),
    ("manage_students", "Manage Students", "Edit or remove students"),
    ("hod_assign_permissions", "HOD Assign Permissions", "Allow HOD to grant permissions"),
    ("manage_groups", "Manage Groups", "Create/edit/delete groups (class sections)"),
    ("assign_group_students", "Assign Group Students", "Assign students to groups"),

    # --- Modules / Courses / Notes ---
    ("create_module", "Create Module", "Add a new module"),
    ("edit_module", "Edit Module", "Modify module details"),
    ("delete_module", "Delete Module", "Delete module"),
    ("view_module", "View Module", "View module content"),
    ("manage_courses", "Manage Courses", "Create or edit courses under modules"),
    ("add_note", "Add Note", "Upload new study material"),
    ("edit_notes", "Edit Notes", "Modify uploaded notes"),
    ("delete_notes", "Delete Notes", "Delete uploaded notes"),
    ("view_notes", "View Notes", "View all notes"),
    ("share_notes", "Share Notes", "Share notes with others"),

    # --- Practice / Questions ---
    ("create_question", "Create Question", "Add new coding or MCQ question"),
    ("edit_question", "Edit Question", "Edit question details"),
    ("delete_question", "Delete Question", "Delete question"),
    ("view_question", "View Question", "View practice or exam question"),
    ("bulk_mcq_upload", "Bulk MCQ Upload", "Upload MCQs in bulk"),
    ("manage_practice_results", "Manage Practice Results", "View or reset practice submissions"),

    # --- Quizzes / Assessments ---
    ("create_quiz", "Create Quiz", "Create a new quiz"),
    ("edit_quiz", "Edit Quiz", "Modify quiz settings"),
    ("delete_quiz", "Delete Quiz", "Delete a quiz"),
    ("view_quiz", "View Quiz", "View quiz information"),
    ("assign_quiz", "Assign Quiz", "Assign quizzes to students"),
    ("submit_quiz", "Submit Quiz", "Submit quiz responses"),
    ("grade_quiz", "Grade Quiz", "Evaluate quiz submissions"),
    ("view_results", "View Results", "View assessment or quiz results"),
    ("reset_quiz_attempt", "Reset Quiz Attempt", "Reset a student’s quiz attempt"),

    # --- Courses ---
    ("create_course", "Create Course", "Add a new course"),
    ("edit_course", "Edit Course", "Edit course details"),
    ("delete_course", "Delete Course", "Delete course"),
    ("view_course", "View Course", "View course content"),

    # --- Notices / Announcements ---
    ("add_notice", "Add Notice", "Post an announcement"),
    ("edit_notice", "Edit Notice", "Edit an announcement"),
    ("delete_notice", "Delete Notice", "Delete announcement"),
    ("view_notice", "View Notice", "View announcements"),
    ("view_announcements", "View Announcements", "Access announcements feed"),
    ("post_feedback", "Post Feedback", "Submit feedback or suggestions"),

    # --- Performance / Reports ---
    ("view_performance", "View Performance", "View student performance data"),
    ("export_performance_data", "Export Performance Data", "Export reports"),
    ("view_leaderboard", "View Leaderboard", "View ranking lists"),
]


ROLE_DEFAULT_PERMISSIONS = {
    "admin": ["*"],  # all permissions

    "hod": [
        "view_dashboard", "view_profile", "edit_profile", "change_password",
        "view_department", "manage_teachers", "manage_students", "assign_roles",
        "manage_permissions", "manage_roles_permissions", "manage_groups",
        "assign_group_students", "create_module", "edit_module", "view_module",
        "create_quiz", "edit_quiz", "delete_quiz", "assign_quiz", "grade_quiz",
        "view_results", "add_note", "edit_notes", "delete_notes", "view_notes",
        "add_notice", "edit_notice", "delete_notice", "view_notice",
        "view_performance", "hod_assign_permissions", "view_announcements",
        "post_feedback"
    ],

    "teacher": [
        "view_dashboard", "view_profile", "edit_profile", "change_password",
        "create_module", "edit_module", "view_module", "create_question",
        "edit_question", "view_question", "create_quiz", "edit_quiz",
        "assign_quiz", "grade_quiz", "view_results", "add_note", "edit_notes",
        "view_notes", "manage_groups", "assign_group_students", "view_notice",
        "view_announcements", "post_feedback"
    ],

    "student": [
        "view_dashboard", "view_profile", "edit_profile", "change_password",
        "view_module", "view_question", "submit_quiz", "view_results",
        "view_notes", "view_notice", "view_announcements", "post_feedback",
        "view_leaderboard"
    ],
}


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

def sync_permissions():
    """Synchronize permission definitions and assign to roles."""
    from codingapp.models import Role, ActionPermission

    try:
        # 1️⃣ Create or update all defined permissions
        created_count = 0
        for code, name, desc in DEFAULT_PERMISSIONS:
            perm, created = ActionPermission.objects.get_or_create(
                code=code,
                defaults={"name": name, "description": desc},
            )
            if not created and (perm.name != name or perm.description != desc):
                perm.name, perm.description = name, desc
                perm.save()
            if created:
                created_count += 1

        print(f"✅ Synced {len(DEFAULT_PERMISSIONS)} permissions ({created_count} new).")

        # 2️⃣ Assign permissions to roles
        for role_name, perm_codes in ROLE_DEFAULT_PERMISSIONS.items():
            role, _ = Role.objects.get_or_create(name=role_name)
            if "*" in perm_codes:
                perms = ActionPermission.objects.all()
            else:
                perms = ActionPermission.objects.filter(code__in=perm_codes)
            role.permissions.set(perms)
            role.save()
            print(f"🎯 Assigned {len(perms)} permissions to {role_name.title()}.")

    except (OperationalError, ProgrammingError):
        # Database not ready (e.g., during migrate)
        print("⚠️ Skipped sync_permissions: database not ready.")

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


class EmailOTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.email} - {self.otp}"


# ================================
# External Coding Profiles
# ================================

class ExternalProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="external_profile"
    )

    # Usernames
    codeforces_username = models.CharField(
        max_length=100, blank=True, null=True
    )

    # Cached stats (JSON)
    codeforces_stats = models.JSONField(
        default=dict, blank=True
    )

    # LeetCode
    leetcode_username = models.CharField(
        max_length=100, blank=True, null=True
    )

    leetcode_stats = models.JSONField(
        default=dict, blank=True
    )
    codechef_username = models.CharField(
    max_length=100,
    blank=True,
    null=True
    )

    codechef_stats = models.JSONField(
        default=dict,
        blank=True
    )
    # HackerRank
    hackerrank_username = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    hackerrank_profile_url = models.URLField(
        blank=True,
        null=True
    )

    hackerrank_verified = models.BooleanField(
        default=False
    )
    hackerrank_stats = models.JSONField(
        default=dict,
        blank=True
    )


    # Last synced timestamp
    last_synced = models.DateTimeField(
        null=True, blank=True
    )

    def __str__(self):
        return f"{self.user.username} - External Profile"


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_external_profile(sender, instance, created, **kwargs):
    if created:
        ExternalProfile.objects.create(user=instance)
