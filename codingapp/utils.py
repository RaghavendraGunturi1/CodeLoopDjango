# codingapp/utils.py
"""
Utility helpers for CodeLoop:
- Role / group access helpers
- Code normalization and light plagiarism utilities (token, AST, winnowing)
- Heuristic AI-generated detection
- Penalty application helpers

Design goals:
- Defensive (safe in Celery workers / management commands)
- No heavy external deps
- Stable function names so other modules/tasks can import them unchanged
"""

from typing import List, Dict, Optional
from collections import deque
from difflib import SequenceMatcher
import ast
import re
import hashlib
import json

# -------------------------
# Role / Group helpers
# -------------------------
def get_user_accessible_groups(user):
    """Return Group queryset visible to this user (based on userprofile.role)."""
    # local import to avoid circular import/time of import in Celery
    from codingapp.models import Group
    profile = getattr(user, "userprofile", None)
    if not profile:
        return Group.objects.none()

    role = profile.role.name.lower() if getattr(profile, "role", None) else ""
    if role == "admin":
        return Group.objects.all()
    if role == "hod":
        return Group.objects.filter(department=profile.department)
    if role == "teacher":
        return Group.objects.filter(teachers=user)
    if role == "student":
        return Group.objects.filter(students=user)
    return Group.objects.none()


def check_object_group_access(request, obj):
    """
    Returns True if request.user can access the object's groups.
    Supports `.groups` (M2M) or `.group` (FK). Falls back to admin-only.
    """
    accessible = get_user_accessible_groups(request.user)
    # M2M
    if hasattr(obj, "groups"):
        return obj.groups.filter(id__in=accessible.values_list("id", flat=True)).exists()
    # FK
    if hasattr(obj, "group") and getattr(obj, "group") is not None:
        return accessible.filter(id=obj.group.id).exists()
    # else admin only
    try:
        return getattr(request.user.userprofile.role, "name", "").lower() == "admin"
    except Exception:
        return False


def deny_access_if_not_allowed(request, obj):
    """Return None if allowed; otherwise render permission page (keeps behaviour of your original helper)."""
    from django.shortcuts import render
    if not check_object_group_access(request, obj):
        return render(request, "codingapp/permission_denied.html", status=403)
    return None


# -------------------------
# Role checks
# -------------------------
def has_role(user, roles):
    try:
        profile = getattr(user, "userprofile", None)
        if not profile or not getattr(profile, "role", None):
            return False
        user_role = profile.role.name.strip().lower()
        allowed = [r.strip().lower() for r in roles]
        return user_role in allowed
    except Exception:
        return False


def is_admin(user):
    return has_role(user, ["admin"])


def is_hod(user):
    return has_role(user, ["hod", "admin"])


def is_teacher(user):
    return has_role(user, ["teacher", "hod", "admin"])


def is_student(user):
    return has_role(user, ["student"])


# -------------------------
# Normalizers
# -------------------------
def normalize_code(src: str, language: str = "python") -> str:
    """
    Light-weight code normalizer used for coarse comparisons:
      - remove single-line comments (# and //)
      - strip C-style block comments /* ... */
      - collapse whitespace
      - convert literal '\n' sequences to real newlines if present
    """
    if not src:
        return ""
    s = src
    try:
        # If string contains literal backslash-n sequences more than real newlines,
        # convert them to actual newlines. This handles some data saved with escapes.
        if "\\n" in s and s.count("\\n") >= s.count("\n"):
            s = s.replace("\\r\\n", "\r\n").replace("\\n", "\n")
    except Exception:
        pass
    # remove comments and block comments
    s = re.sub(r'(?m)#.*$', '', s)
    s = re.sub(r'(?m)//.*$', '', s)
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    # collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_code_text(code: str) -> str:
    """Conservative normalizer: removes blank/comment-only lines but preserves line breaks/structure."""
    if not code:
        return ""
    try:
        txt = code.replace("\r\n", "\n").strip()
        lines = []
        for line in txt.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#") or s.startswith("//"):
                continue
            lines.append(line)
        return "\n".join(lines)
    except Exception:
        return code or ""


# -------------------------
# Penalty mapping helper
# -------------------------
def penalty_factor_from_plagiarism(pct: float, no_penalty_up_to: float = 35.0, full_zero_at: float = 85.0) -> float:
    """
    Map plagiarism percent to penalty factor in [0.0, 1.0].
    Linear ramp between no_penalty_up_to and full_zero_at.
    """
    try:
        p = float(pct or 0.0)
    except Exception:
        p = 0.0
    if p <= no_penalty_up_to:
        return 1.0
    if p >= full_zero_at:
        return 0.0
    return round((full_zero_at - p) / (full_zero_at - no_penalty_up_to), 4)


# -------------------------
# Tokenization & Winnowing
# -------------------------
# keep identifiers, numbers and common operators
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+|==|!=|<=|>=|->|::|&&|\|\||[^\s\w]", flags=re.M)


def remove_string_literals(code: str) -> str:
    """Replace string literal contents with empty quotes (best-effort)."""
    if not code:
        return ""
    try:
        # basic handling of single/double/triple quoted strings
        # note: not a full parser; this is a heuristic for lightweight comparisons.
        # remove triple quotes first
        code = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '""', code)
        code = re.sub(r'(["\'])(?:(?=(\\?))\2.)*?\1', '""', code, flags=re.S)
        return code
    except Exception:
        return code


def tokenize_code(code: str) -> List[str]:
    """Return tokens from code using regex. Falls back to whitespace split if issues occur."""
    if not code:
        return []
    try:
        code2 = remove_string_literals(code)
        toks = _TOKEN_RE.findall(code2)
        return toks if toks else list(filter(None, re.split(r'\s+', code2)))
    except Exception:
        return list(filter(None, re.split(r'\s+', code)))


def k_grams(tokens: List[str], k: int = 5):
    dq = deque(maxlen=k)
    for t in tokens:
        dq.append(t)
        if len(dq) == k:
            yield " ".join(dq)


def hash_kgram(s: str) -> int:
    """64-bit-ish int hash of k-gram using md5 hex (first 16 hex chars)."""
    h = hashlib.md5(s.encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def winnowing_fingerprint(code: str, k: int = 5, w: int = 4) -> set:
    """
    Basic winnowing: produce set of fingerprints (ints).
    If code too short, return set of all k-gram hashes.
    """
    tokens = tokenize_code(code)
    kgs = list(k_grams(tokens, k=k))
    if not kgs:
        return set()
    hashes = [hash_kgram(x) for x in kgs]
    if w <= 0 or w > len(hashes):
        return set(hashes)
    fingerprints = set()
    for i in range(len(hashes) - w + 1):
        window = hashes[i:i + w]
        m = min(window)
        fingerprints.add(m)
    if not fingerprints:
        fingerprints = set(hashes)
    return fingerprints


def token_similarity(a: str, b: str) -> float:
    """Jaccard-like similarity between two fingerprint sets (0..1)."""
    try:
        fa = winnowing_fingerprint(a)
        fb = winnowing_fingerprint(b)
        if not fa or not fb:
            return 0.0
        inter = len(fa & fb)
        union = len(fa | fb)
        if union == 0:
            return 0.0
        return inter / union
    except Exception:
        return 0.0


# -------------------------
# Structural (AST) similarity
# -------------------------
def python_ast_normalize(code: str) -> str:
    """Return a sequence of AST node type names for Python code. Empty on parse error."""
    if not code:
        return ""
    try:
        tree = ast.parse(code)
    except Exception:
        return ""
    parts = []
    for node in ast.walk(tree):
        parts.append(type(node).__name__)
    return " ".join(parts)


def structural_similarity(a: str, b: str) -> float:
    """Compare AST node sequences using SequenceMatcher (0..1)."""
    try:
        sa = python_ast_normalize(a)
        sb = python_ast_normalize(b)
        if not sa or not sb:
            return 0.0
        return SequenceMatcher(None, sa, sb).ratio()
    except Exception:
        return 0.0


# -------------------------
# Heuristic AI detection
# -------------------------
def heuristic_ai_score(code: str) -> float:
    """
    Heuristic probability (0..1) that a code snippet looks 'AI generated'.
    Not definitive — used as a signal in ensemble.
    """
    if not code:
        return 0.0
    txt = normalize_code_text(code)
    tokens = tokenize_code(txt)
    ntokens = max(1, len(tokens))
    uniq = len(set(tokens))
    diversity = uniq / ntokens
    diversity_score = 1.0 - min(1.0, diversity)   # smaller diversity -> higher suspicion

    boilerplate_markers = [
        "if __name__ == '__main__'",
        "Example:",
        "Usage:",
        "def main(",
        "print(",
        "return 0",
    ]
    bp_count = sum(1 for p in boilerplate_markers if p in txt)
    bp_score = min(1.0, bp_count / 3.0)

    small_vars = sum(1 for t in tokens if len(t) <= 2)
    small_var_score = min(1.0, small_vars / 15.0)

    score = (0.55 * diversity_score) + (0.3 * bp_score) + (0.15 * small_var_score)
    return max(0.0, min(1.0, score))


# -------------------------
# Ensemble plagiarism signal
# -------------------------
def compute_ensemble_plagiarism(code: str,
                                other_codes: List[str],
                                *,
                                short_length_threshold: int = 25,
                                token_weight: float = 0.4,
                                struct_weight: float = 0.35,
                                embed_weight: float = 0.25,
                                ai_boost: float = 0.15) -> Dict:
    """
    Compute combined plagiarism signals. Returns a dict:
      { token_similarity, structural_similarity, embedding_similarity, ai_generated_prob, plag_percent }
    All similarity components are in range 0..1 (plag_percent is 0..100).
    Embeddings placeholder uses structural similarity when no embedding model is present.
    """
    best_token = 0.0
    best_struct = 0.0
    best_embed = 0.0

    code = code or ""
    other_codes = other_codes or []

    for other in other_codes:
        if not other:
            continue
        try:
            t = token_similarity(code, other)
        except Exception:
            t = 0.0
        try:
            s = structural_similarity(code, other)
        except Exception:
            s = 0.0
        e = s  # placeholder for embedding similarity

        if t > best_token:
            best_token = t
        if s > best_struct:
            best_struct = s
        if e > best_embed:
            best_embed = e

    ai_prob = heuristic_ai_score(code)  # 0..1
    num_tokens = max(0, len(tokenize_code(code)))

    length_factor = 1.0
    if short_length_threshold > 0 and num_tokens < short_length_threshold:
        length_factor = min(1.0, float(num_tokens) / float(short_length_threshold))

    base = (best_token * token_weight) + (best_struct * struct_weight) + (best_embed * embed_weight)
    base = base * (1.0 + ai_boost * ai_prob)
    base = base * length_factor

    plag_percent = round(min(1.0, base) * 100.0, 2)

    return {
        "token_similarity": round(best_token, 4),
        "structural_similarity": round(best_struct, 4),
        "embedding_similarity": round(best_embed, 4),
        "ai_generated_prob": round(ai_prob, 4),
        "plag_percent": plag_percent
    }


# -------------------------
# Penalty application helper
# -------------------------
def apply_plagiarism_penalty(raw_marks: float, plagiarism_percent: float, code: Optional[str] = None, question=None) -> float:
    """
    Map raw_marks to adjusted marks based on plagiarism_percent.
    Allows higher tolerance for trivial/short solutions.
    """
    try:
        raw_marks = float(raw_marks or 0)
    except Exception:
        raw_marks = 0.0

    if raw_marks <= 0:
        return 0.0

    code = code or ""
    lines = [ln for ln in code.splitlines() if ln.strip()]
    non_empty_lines = len(lines)
    char_len = len("".join(lines))

    # trivial heuristic
    is_trivial = (non_empty_lines <= 3) or (char_len <= 40)

    if is_trivial:
        safe = 90.0
        hard_zero = 100.0
    else:
        safe = 35.0
        hard_zero = 85.0

    try:
        p = float(plagiarism_percent or 0.0)
    except Exception:
        p = 0.0

    if p <= safe:
        return round(raw_marks, 2)
    if p >= hard_zero:
        return 0.0

    factor = (hard_zero - p) / float(hard_zero - safe)
    adjusted = raw_marks * factor
    return round(adjusted, 2)


# -------------------------
# Convenience debug helper (not run on import)
# -------------------------
def _quick_self_test():
    a = "a = int(input())\nb = int(input())\nprint(a + b)"
    b = "x = int(input())\ny = int(input())\nprint(x+y)"
    c = "def foo():\n    return 42"
    print("token sim a<>b:", token_similarity(a, b))
    print("struct sim a<>b:", structural_similarity(a, b))
    print("heuristic ai a:", heuristic_ai_score(a))
    print("ensemble a vs [b,c]:", compute_ensemble_plagiarism(a, [b, c]))


import re
from django.core.exceptions import ValidationError

ROLL_REGEX = r'^[0-9]{2}[A-Z0-9]{4}[0-9]{2}[A-Z0-9]{2}$'

def validate_roll_number(roll):
    roll = roll.upper()

    if len(roll) != 10:
        raise ValidationError("Roll number must be exactly 10 characters.")

    if not re.match(ROLL_REGEX, roll):
        raise ValidationError(
            "Invalid roll number format. Example: 23AGCS01A2"
        )

    return roll


import random

def generate_otp():
    return str(random.randint(100000, 999999))



from django.core.mail import send_mail
from django.conf import settings
# codingapp/utils.py
from django.core.mail import send_mail
from django.conf import settings

def send_otp_email(email, otp):
    subject = "CodeLoop | Email Verification OTP"
    message = f"""
Dear User,

Your One-Time Password (OTP) for CodeLoop registration is:

🔐 {otp}

This OTP is valid for 10 minutes.
Do NOT share it with anyone.

Regards,
CodeLoop Team
"""
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False
    )


# ==============================
# PERFORMANCE HELPERS
# ==============================

from django.contrib.auth import get_user_model
from django.db.models import Sum
from codingapp.models import (
    Group,
    AssessmentSubmission,
    QuizSubmission
)

User = get_user_model()


def get_visible_students(user):
    profile = getattr(user, "userprofile", None)
    if not profile or not profile.role:
        return User.objects.none()

    role = profile.role.name.lower()

    if role == "admin":
        return User.objects.filter(userprofile__role__name="Student")

    if role == "hod":
        return User.objects.filter(
            userprofile__role__name="Student",
            userprofile__department=profile.department
        )

    if role == "teacher":
        student_ids = Group.objects.filter(
            teachers=user
        ).values_list("students", flat=True)

        return User.objects.filter(id__in=student_ids)

    return User.objects.none()

from django.db import models
from django.db.models import Max
from collections import defaultdict
from collections import defaultdict

def get_student_performance(student):
    from codingapp.models import (
        ExternalProfile,
        AssessmentSubmission,
    )

    # -----------------------------------
    # ASSESSMENT → QUESTION-WISE HANDLING
    # -----------------------------------
    submissions = (
        AssessmentSubmission.objects
        .filter(user=student)
        .select_related("assessment", "question")
        .order_by("assessment_id", "question_id", "-submitted_at")
    )

    # (assessment_id, question_id) → latest submission
    latest_per_question = {}

    for sub in submissions:
        key = (sub.assessment_id, sub.question_id)
        if key not in latest_per_question:
            latest_per_question[key] = sub

    # assessment_id → aggregated data
    assessment_map = defaultdict(lambda: {
        "name": "",
        "score": 0,
        "submitted_at": None,
    })

    for (assessment_id, _), sub in latest_per_question.items():
        entry = assessment_map[assessment_id]
        entry["name"] = sub.assessment.title
        entry["score"] += sub.score or 0

        if not entry["submitted_at"] or sub.submitted_at > entry["submitted_at"]:
            entry["submitted_at"] = sub.submitted_at

    assessments = list(assessment_map.values())
    assessment_score = sum(a["score"] for a in assessments)

    # -----------------------
    # QUIZ (OPTIONAL)
    # -----------------------
    quiz_score = 0
    internal_score = assessment_score + quiz_score

    # -----------------------
    # EXTERNAL PROFILES (FIXED)
    # -----------------------
    external = {
        "codeforces": {},
        "leetcode": {},
        "codechef": {},
        "hackerrank": None,  # IMPORTANT: default is None
    }

    profile = ExternalProfile.objects.filter(user=student).first()

    if profile:
        if profile.codeforces_stats:
            external["codeforces"] = profile.codeforces_stats

        if profile.leetcode_stats:
            external["leetcode"] = profile.leetcode_stats

        if profile.codechef_stats:
            external["codechef"] = profile.codechef_stats

        if profile.hackerrank_username:
            external["hackerrank"] = {
                "username": profile.hackerrank_username,
                "profile_url": f"https://www.hackerrank.com/{profile.hackerrank_username}"
            }

    return {
        "student": student,
        "assessments": assessments,
        "assessment_score": assessment_score,
        "quiz_score": quiz_score,
        "internal_score": internal_score,
        "external": external,
    }
