# codingapp/tasks.py
from celery import shared_task
import requests
import json
import logging
from django.conf import settings
from .models import Submission, AssessmentSubmission, Question # Import models you need to update
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Submission, AssessmentSubmission, Question, Assessment # 👈 FIX: Added 'Assessment' import

logger = logging.getLogger(__name__)

# NOTE: The execute_code helper from views.py is moved/modified here
def run_piston_api(code, language, test_case_input):
    """
    Internal helper to execute a single test case against the Piston API.
    """
    payload = {
        "language": language,
        "version": "*",
        "files": [{"name": "solution", "content": code}],
        "stdin": test_case_input
    }

    try:
        resp = requests.post(settings.PISTON_API_URL, json=payload, timeout=settings.PISTON_API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        stdout = data.get("run", {}).get("stdout", "").strip()
        stderr = data.get("run", {}).get("stderr", "").strip()
        return stdout, stderr

    except requests.exceptions.RequestException as e:
        logger.error(f"Piston API request failed: {e}", exc_info=True)
        return "", f"Piston API Error: Could not connect or request failed. ({e})"


def check_test_cases(code, language, test_cases):
    """
    Runs all test cases and returns a structured result list.
    """
    results = []
    all_accepted = True
    final_error_output = None

    for test in test_cases or []:
        input_data = test.get("input", "")
        expected_lines = [line.strip() for line in test.get("expected_output", []) if line.strip()]

        stdout, stderr = run_piston_api(code, language, input_data)

        if stderr:
            status = "Error"
            error_message = stderr
            all_accepted = False
            final_error_output = stderr
        else:
            actual_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            
            # Simple line-by-line comparison
            if len(actual_lines) != len(expected_lines):
                status = "Rejected"
                error_message = f"Output mismatch: Expected {len(expected_lines)} lines, got {len(actual_lines)}."
                all_accepted = False
            else:
                mismatches = [f"Line {i+1}: Expected '{expected}', got '{actual}'"
                              for i, (actual, expected) in enumerate(zip(actual_lines, expected_lines))
                              if actual != expected]
                
                if mismatches:
                    status = "Rejected"
                    error_message = "; ".join(mismatches)
                    all_accepted = False
                else:
                    status = "Accepted"
                    error_message = ""
        
        results.append({
            "input": input_data,
            "expected_output": expected_lines,
            "actual_output": [line.strip() for line in stdout.splitlines() if line.strip()],
            "status": status,
            "error_message": error_message
        })
        
        if final_error_output:
            break

    # Return results for the view to fetch
    return {
        'results': results,
        'status': "Accepted" if all_accepted else "Rejected" if not final_error_output else "Error",
        'error': final_error_output,
        'score': sum(1 for r in results if r["status"] == "Accepted")
    }


# 🔥 Primary Celery Task for Practice Submissions
@shared_task(bind=True)
def process_practice_submission(self, user_id, question_id, code, language):
    """
    Task to execute user code for a practice question and save the results.
    """
    try:
        user = User.objects.get(pk=user_id)
        question = Question.objects.get(pk=question_id)
    except (User.DoesNotExist, Question.DoesNotExist):
        return {'status': 'Error', 'error': 'User or Question not found.'}

    # Run the synchronous logic
    task_results = check_test_cases(code, language, question.test_cases)
    
    # Save the final submission result to the database
    submission, _ = Submission.objects.update_or_create(
        user=user,
        question=question,
        defaults={
            'code': code,
            'language': language,
            'status': task_results['status'],
            'output': json.dumps(task_results['results']), # Store the detailed results as JSON
            'error': task_results['error'] or "",
        }
    )

    # Logic to mark module completed (copied from views.py)
    if task_results['status'] == "Accepted" and question.module:
        module_questions = question.module.questions.all()
        solved_count = Submission.objects.filter(
            user=user,
            question__in=module_questions,
            status="Accepted"
        ).values("question").distinct().count()

        if solved_count == module_questions.count():
            from .models import ModuleCompletion
            ModuleCompletion.objects.get_or_create(user=user, module=question.module)
            
    # Return the full task result for API polling
    return {
        'task_id': self.request.id,
        'final_status': submission.status,
        'results': task_results['results'],
        'error': task_results['error']
    }


# 🔥 Primary Celery Task for Assessment Submissions
@shared_task(bind=True)
def process_assessment_submission(self, user_id, assessment_id, question_id, code, language):
    """
    Task to execute user code for an assessment question and save the score.
    """
    try:
        user = User.objects.get(pk=user_id)
        assessment = Assessment.objects.get(pk=assessment_id)
        question = Question.objects.get(pk=question_id)
    except (User.DoesNotExist, Assessment.DoesNotExist, Question.DoesNotExist):
        return {'status': 'Error', 'error': 'User, Assessment, or Question not found.'}

    # Run the synchronous logic
    task_results = check_test_cases(code, language, question.test_cases)
    score = task_results['score']
    
    # Save the final submission result to the database
    AssessmentSubmission.objects.update_or_create(
        user=user, assessment=assessment, question=question,
        defaults={
            'code': code,
            'language': language,
            'output': json.dumps(task_results['results']),
            'error': task_results['error'] or "",
            'score': score
        }
    )

    # Return results for API polling
    return {
        'task_id': self.request.id,
        'final_status': task_results['status'],
        'results': task_results['results'],
        'error': task_results['error']
    }