# codingapp/tasks.py
"""
Celery tasks for CodeLoop:
- practice submission runner (via Piston)
- assessment submission processing (testcases, plagiarism signals, penalty, save)
"""

import json
import logging
from typing import Tuple, List

from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from celery import shared_task

logger = logging.getLogger(__name__)
User = get_user_model()

# Local model imports (used in tasks)
from .models import Submission, AssessmentSubmission, Question, Assessment

# Try to import helpers from utils / tasks_helpers
from .utils import compute_ensemble_plagiarism, apply_plagiarism_penalty
try:
    # preferred: a lightweight runner placed in codingapp/tasks_helpers.py
    from .tasks_helpers import check_test_cases  # type: ignore
except Exception:
    check_test_cases = None
    logger.debug("codingapp.tasks_helpers.check_test_cases not available; will use fallback runner.")


# ---------------------------
# Small execution helper (Piston)
# ---------------------------
def run_piston_api(code: str, language: str, test_case_input: str) -> Tuple[str, str]:
    """
    Execute code using configured Piston API (or return error strings).
    Returns (stdout, stderr).
    """
    PISTON_URL = getattr(settings, "PISTON_API_URL", None)
    TIMEOUT = getattr(settings, "PISTON_API_TIMEOUT", 10)

    if not PISTON_URL:
        return "", "Piston API URL not configured."

    payload = {
        "language": language,
        "version": "*",
        "files": [{"name": "solution", "content": code}],
        "stdin": test_case_input
    }

    try:
        import requests  # local import to avoid top-level dependency if not used
        resp = requests.post(PISTON_URL, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        run_info = data.get("run", {}) if isinstance(data, dict) else {}
        stdout = (run_info.get("stdout") or "").strip()
        stderr = (run_info.get("stderr") or "").strip()
        return stdout, stderr
    except Exception as exc:
        logger.exception("Piston API call failed")
        return "", f"Piston API Error: {str(exc)}"


# ---------------------------
# Fallback check_test_cases (only used if tasks_helpers not present)
# ---------------------------
def _fallback_check_test_cases(code: str, language: str, test_cases):
    """
    Minimal runner that uses Piston API for each test case.
    Structured return consistent with your other code:
      { 'score': int, 'results': [...], 'error': '', 'status': 'Accepted'/'Rejected'/'Error' }
    """
    results = []
    passed = 0
    overall_error = None

    if language is None:
        language = "python"

    # If Piston not configured, fail fast
    if not getattr(settings, "PISTON_API_URL", None):
        return {
            "score": 0,
            "results": [],
            "error": "Piston runner not configured on server.",
            "status": "Error"
        }

    try:
        for tc in (test_cases or []):
            input_data = tc.get("input", "")
            expected = tc.get("expected_output", []) or []
            if isinstance(expected, str):
                expected_lines = [expected.strip()]
            else:
                expected_lines = [str(x).strip() for x in expected]

            stdout, stderr = run_piston_api(code, language, input_data)

            actual_lines = [ln.strip() for ln in (stdout or "").splitlines() if ln.strip()]
            status = "Accepted"
            error_message = ""

            if stderr:
                status = "Error"
                error_message = stderr
            else:
                # tolerant compare
                if expected_lines == actual_lines:
                    status = "Accepted"
                else:
                    if " ".join(expected_lines).strip() == " ".join(actual_lines).strip():
                        status = "Accepted"
                    else:
                        status = "Rejected"
                        error_message = f"Expected {expected_lines}, got {actual_lines}"

            if status == "Accepted":
                passed += 1

            results.append({
                "input": input_data,
                "expected_output": expected_lines,
                "actual_output": actual_lines,
                "status": status,
                "error_message": error_message
            })

        final_status = "Accepted" if (passed == len(test_cases or []) and len(test_cases or []) > 0) else "Rejected"
        return {"score": passed, "results": results, "error": overall_error or "", "status": final_status}
    except Exception as e:
        logger.exception("Fallback check_test_cases failed")
        return {"score": 0, "results": [], "error": str(e), "status": "Error"}


# Pick effective check_test_cases (prefer tasks_helpers)
if not check_test_cases:
    check_test_cases = _fallback_check_test_cases


# ---------------------------
# Practice submission task
# ---------------------------
@shared_task(bind=True)
def process_practice_submission(self, user_id, question_id, code, language):
    """
    Evaluate code for a practice question and save to Submission model.
    Returns task result dict to allow polling.
    """
    try:
        user = User.objects.get(pk=user_id)
        question = Question.objects.get(pk=question_id)
    except Exception:
        logger.exception("Practice submission: user/question lookup failed")
        return {"status": "Error", "error": "User or Question not found."}

    try:
        task_results = check_test_cases(code, language, question.test_cases)
    except Exception as e:
        logger.exception("Practice check_test_cases failed")
        task_results = {"score": 0, "results": [], "error": str(e), "status": "Error"}

    # Save or update Submission row
    try:
        defaults = {
            "code": code,
            "language": language,
            "status": task_results.get("status", "Error"),
            "output": json.dumps(task_results.get("results", [])),
            "error": task_results.get("error", "") or ""
        }
        submission, _ = Submission.objects.update_or_create(
            user=user,
            question=question,
            defaults=defaults
        )
    except Exception:
        logger.exception("Saving practice Submission failed")
        return {"status": "Error", "error": "DB save failed for practice submission."}

    # Mark module completion if question.module exists and all module questions solved
    try:
        if task_results.get("status") == "Accepted" and getattr(question, "module", None):
            module_questions = question.module.questions.all()
            solved_count = Submission.objects.filter(
                user=user,
                question__in=module_questions,
                status="Accepted"
            ).values("question").distinct().count()

            if solved_count == module_questions.count():
                from .models import ModuleCompletion
                ModuleCompletion.objects.get_or_create(user=user, module=question.module)
    except Exception:
        logger.exception("Module completion check failed for practice submission")

    return {
        "task_id": self.request.id,
        "final_status": submission.status,
        "results": task_results.get("results", []),
        "error": task_results.get("error", "")
    }


# ---------------------------
# Assessment submission task
# ---------------------------
@shared_task(bind=True)
def process_assessment_submission(self, user_id, assessment_id, question_id, code, language):
    """
    Evaluate an assessment coding submission, compute plagiarism signals,
    apply penalty and save the submission row into AssessmentSubmission.

    Returns a dict suitable for polling by the frontend.
    """
    try:
        user = User.objects.get(pk=user_id)
        assessment = Assessment.objects.get(pk=assessment_id)
        question = Question.objects.get(pk=question_id)
    except Exception:
        logger.exception("Assessment submission: lookup failed")
        return {"status": "Error", "error": "User/Assessment/Question not found."}

    # 1) Run test cases
    try:
        task_results = check_test_cases(code, language, question.test_cases)
    except Exception as e:
        logger.exception("Assessment check_test_cases failed")
        task_results = {"score": 0, "results": [], "error": str(e), "status": "Error"}

    raw_passed = int(task_results.get("score", 0) or 0)
    total_tests = len(question.test_cases or [])

    # Decide partial scoring behaviour via settings
    # Default: partial marks enabled (proportional to number of passed tests)
    PARTIAL_MARKS = getattr(settings, "ASSESSMENT_PARTIAL_MARKS", True)

    if total_tests > 0:
        if PARTIAL_MARKS:
            marks_before_penalty = round((raw_passed / total_tests) * 5.0, 2)
        else:
            marks_before_penalty = 5 if raw_passed == total_tests else 0
    else:
        # No testcases defined: fallback conservative behaviour
        marks_before_penalty = 5.0 if raw_passed > 0 else 0.0

    results_json = json.dumps(task_results.get("results", []))
    error_message = task_results.get("error", "") or ""
    final_status = task_results.get("status", "Error")

    # 2) Plagiarism ensemble: compare to other submissions (cap for perf)
    plagiarism_percent = 0.0
    structural_sim = 0.0
    token_sim = 0.0
    embedding_sim = 0.0
    ai_prob = 0.0

    try:
        MAX_COMPARE = getattr(settings, "PLAGIARISM_COMPARE_LIMIT", 200)
        other_codes_qs = (
            AssessmentSubmission.objects
            .filter(assessment=assessment, question=question)
            .exclude(user=user)
            .order_by("-submitted_at")
            .values_list("code", flat=True)[:MAX_COMPARE]
        )
        other_codes = [c for c in other_codes_qs if c]
        if other_codes:
            signals = compute_ensemble_plagiarism(code or "", other_codes)
            plagiarism_percent = float(signals.get("plag_percent", 0.0))
            token_sim = float(signals.get("token_similarity", 0.0))
            structural_sim = float(signals.get("structural_similarity", 0.0))
            embedding_sim = float(signals.get("embedding_similarity", 0.0))
            ai_prob = float(signals.get("ai_generated_prob", 0.0))
        else:
            # no comparators -> everything remains zero
            plagiarism_percent = 0.0
    except Exception:
        logger.exception("Plagiarism computation failed for assessment submission")
        plagiarism_percent = 0.0
        token_sim = structural_sim = embedding_sim = ai_prob = 0.0

    # 3) Apply plagiarism penalty
    try:
        final_marks = apply_plagiarism_penalty(
            raw_marks=marks_before_penalty,
            plagiarism_percent=plagiarism_percent,
            code=code,
            question=question
        )
    except Exception:
        logger.exception("apply_plagiarism_penalty failed")
        final_marks = marks_before_penalty

    # 4) Persist submission (update_or_create). Build defaults dict carefully.
    try:
        # Build defaults (do NOT include 'updated_at' if you don't want to force it)
        defaults = {
            "code": code,
            "language": language,
            "output": results_json,
            "error": error_message,
            "score": final_marks,
            "raw_score": marks_before_penalty,
            "plagiarism_percent": plagiarism_percent,
            "structural_similarity": structural_sim,
            "token_similarity": token_sim,
            "embedding_similarity": embedding_sim,
            "ai_generated_prob": ai_prob,
            "submitted_at": timezone.now(),
        }
        # Remove None values so we don't pass invalid values into DB
        defaults = {k: v for k, v in defaults.items() if v is not None}

        AssessmentSubmission.objects.update_or_create(
            user=user,
            assessment=assessment,
            question=question,
            defaults=defaults
        )
    except Exception as e:
        logger.exception("Saving AssessmentSubmission failed")
        return {
            "status": "Error",
            "error": f"DB save failed: {str(e)}",
            "results": task_results.get("results", []),
            "plagiarism_percent": plagiarism_percent,
            "score": final_marks
        }

    # 5) Return results for frontend polling
    return {
        "task_id": self.request.id,
        "final_status": final_status,
        "results": task_results.get("results", []),
        "error": error_message,
        "plagiarism_percent": plagiarism_percent,
        "structural_similarity": structural_sim,
        "token_similarity": token_sim,
        "embedding_similarity": embedding_sim,
        "ai_generated_prob": ai_prob,
        "raw_score": marks_before_penalty,
        "score": final_marks,
    }

from celery import shared_task
from django.utils import timezone

from codingapp.models import ExternalProfile
from codingapp.external_services.codeforces import fetch_codeforces_stats
from celery import shared_task
from django.utils import timezone

from codingapp.models import ExternalProfile
from codingapp.external_services.codeforces import fetch_codeforces_stats
from codingapp.external_services.leetcode import fetch_leetcode_stats
from codingapp.external_services.codechef import fetch_codechef_stats
from codingapp.external_services.hackerrank import fetch_hackerrank_stats




@shared_task(bind=True, max_retries=3)
def sync_external_profiles(self, user_id):
    """
    Unified sync task for ALL external platforms.
    Safe, retryable, and extensible.
    """
    try:
        profile = ExternalProfile.objects.get(user_id=user_id)

        updated = False

        # -------------------------
        # Codeforces
        # -------------------------
        if profile.codeforces_username:
            cf_stats = fetch_codeforces_stats(profile.codeforces_username)
            if cf_stats:
                profile.codeforces_stats = cf_stats
                updated = True

        # -------------------------
        # LeetCode
        # -------------------------
        if profile.leetcode_username:
            lc_stats = fetch_leetcode_stats(profile.leetcode_username)
            if lc_stats:
                profile.leetcode_stats = lc_stats
                updated = True

        # -------------------------
        # CodeChef
        # -------------------------
        if profile.codechef_username:
            cc = fetch_codechef_stats(profile.codechef_username)
            if cc:
                profile.codechef_stats = cc
                updated = True

        print("HACKERRANK USERNAME:", profile.hackerrank_username)
        # -------------------------
        # HackerRank (Hackos + Badges)
        # -------------------------
        if profile.hackerrank_username:
            print("ENTERING HACKERRANK BLOCK")

            hr = fetch_hackerrank_stats(profile.hackerrank_username)
            print("HACKERRANK FETCH RESULT:", hr)

            if hr:
                profile.hackerrank_stats = hr
                profile.hackerrank_profile_url = hr.get("profile_url")
                profile.hackerrank_verified = True
                updated = True


        # -------------------------
        # Save only if something changed
        # -------------------------
        if updated:
            profile.last_synced = timezone.now()
            profile.save()

        print("SYNC TASK STARTED FOR USER:", user_id)

        if profile.codeforces_username:
            print("FETCHING CODEFORCES:", profile.codeforces_username)

        if profile.leetcode_username:
            print("FETCHING LEETCODE:", profile.leetcode_username)


        return "External profiles synced"

    except ExternalProfile.DoesNotExist:
        return "External profile does not exist"

    except Exception as e:
        # Retry on temporary failures (network, API, etc.)
        raise self.retry(exc=e, countdown=30)
