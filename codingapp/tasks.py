# In codingapp/tasks.py
import requests
import logging
import json
from celery import shared_task
from django.conf import settings
from .models import Submission, ModuleCompletion, Question
# --- ACTION 1: Import the necessary libraries for Channels ---
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

@shared_task
def execute_code_task(submission_id):
    """
    Background task to execute code, save the results, AND send a real-time update.
    """
    try:
        submission = Submission.objects.get(id=submission_id)
        question = submission.question
    except Submission.DoesNotExist:
        logger.error(f"Submission with ID {submission_id} not found.")
        return

    # (Your existing Step 2: Code execution logic remains exactly the same)
    results = []
    error_output = None
    PISTON_API_URL = settings.PISTON_API_URL
    # ... (for loop to call piston API) ...
    # This logic is correct and does not need to change.
    for test in question.test_cases or []:
        payload = {
            "language": submission.language,
            "version": "*",
            "files": [{"name": "solution", "content": submission.code}],
            "stdin": test.get("input", "")
        }
        try:
            resp = requests.post(PISTON_API_URL, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            stdout = data.get("run", {}).get("stdout", "").strip()
            stderr = data.get("run", {}).get("stderr", "").strip()

            actual_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            expected_lines = test.get("expected_output", [])

            if len(actual_lines) != len(expected_lines):
                status = "Rejected"
                error_message = f"Output had {len(actual_lines)} lines, but expected {len(expected_lines)}."
            else:
                mismatches = [
                    f"Line {i+1}: Expected '{expected}', got '{actual}'"
                    for i, (actual, expected) in enumerate(zip(actual_lines, expected_lines))
                    if actual != expected
                ]
                if mismatches:
                    status = "Rejected"
                    error_message = "; ".join(mismatches)
                else:
                    status = "Accepted"
                    error_message = ""
            
            if stderr:
                status = "Error"
                error_message = stderr

            results.append({
                "input": test.get("input", ""),
                "expected_output": expected_lines,
                "actual_output": actual_lines,
                "status": status,
                "error_message": error_message
            })
        except requests.exceptions.RequestException as e:
            logger.error(f"Piston API request failed for submission {submission_id}: {e}", exc_info=True)
            results.append({"status": "Error", "error_message": f"API request failed: {e}"})
            error_output = f"API request failed: {e}"
            break

    # Step 3: Update the Submission record (Your existing code is correct)
    all_accepted = results and all(r["status"] == "Accepted" for r in results)
    submission.status = "Accepted" if all_accepted else "Rejected"
    submission.output = json.dumps({"results": results}) # Use json.dumps
    submission.error = error_output
    submission.save()

    # --- ACTION 2: This is the critical block that was missing ---
    # After saving, get the channel layer and send the final results
    # to the specific "room" for this submission.
    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            f'submission_{submission_id}',  # This must match the group name in your consumer
            {
                'type': 'submission_update',  # This calls the `submission_update` method in consumers.py
                'status': submission.status,
                'results': results,
            }
        )
    # ---------------------------------------------------

    # Step 4: Handle module completion logic (Your existing code is correct)
    if all_accepted and question.module:
        module_questions = Question.objects.filter(module=question.module)
        solved_count = Submission.objects.filter(
            user=submission.user,
            question__in=module_questions,
            status="Accepted"
        ).values("question").distinct().count()

        if solved_count == module_questions.count():
            ModuleCompletion.objects.get_or_create(user=submission.user, module=question.module)

    logger.info(f"Successfully processed and sent update for submission ID: {submission_id}")