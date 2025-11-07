import requests
import logging
import json # <-- ADD json import
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings
import csv # <--- NEW IMPORT
from django.utils.text import slugify # <--- NEW IMPORT
from celery.result import AsyncResult # <-- ADD CELERY IMPORT
from celery.result import AsyncResult 
from .tasks import process_practice_submission, process_assessment_submission # (and other tasks)
from .models import (
    Question, Submission, Module,
    Assessment, AssessmentQuestion, AssessmentSubmission,
    AssessmentSession
)
from .forms import ModuleForm, QuestionForm
from codingapp import models
from codingapp.models import Department, Role, ActionPermission, UserProfile


# Piston (code execution) API endpoint
#PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"
#PISTON_API_URL = "http://localhost:2000/api/v2/execute"
PISTON_API_URL = settings.PISTON_API_URL
SUPPORTED_LANGUAGES = ["python", "c", "cpp", "java", "javascript"]

logger = logging.getLogger(__name__)



from django.contrib.auth.views import LoginView

class CustomLoginView(LoginView):
    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session['force_splash'] = True
        return response


def is_admin(user):
    return user.is_staff

import requests
import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)

# def execute_code(code, language, test_cases):
#     """
#     Helper to run code via Piston and collect results, with improved error handling.
#     """
#     results = []
#     error_output = None

#     for test in test_cases or []:
#         payload = {
#             "language": language,
#             "version": "*",
#             "files": [{"name": "solution", "content": code}],
#             "stdin": test.get("input", "")
#         }

#         try:
#             resp = requests.post(PISTON_API_URL, json=payload, timeout=10)
#             resp.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

#             data = resp.json()
#             stdout = data.get("run", {}).get("stdout", "").strip()
#             stderr = data.get("run", {}).get("stderr", "").strip()

#             actual_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
#             expected_lines = test.get("expected_output", [])

#             if stderr:
#                 status = "Error"
#                 error_message = stderr
#             elif len(actual_lines) != len(expected_lines):
#                 status = "Rejected"
#                 error_message = f"Output mismatch: Expected {len(expected_lines)} lines, but got {len(actual_lines)}."
#             else:
#                 mismatches = [f"Line {i+1}: Expected '{expected}', got '{actual}'"
#                               for i, (actual, expected) in enumerate(zip(actual_lines, expected_lines))
#                               if actual != expected]
#                 if mismatches:
#                     status = "Rejected"
#                     error_message = "; ".join(mismatches)
#                 else:
#                     status = "Accepted"
#                     error_message = ""

#             results.append({
#                 "input": test.get("input", ""),
#                 "expected_output": expected_lines,
#                 "actual_output": actual_lines,
#                 "status": status,
#                 "error_message": error_message
#             })

#         except requests.exceptions.Timeout:
#             logger.error("Piston API request timed out.", exc_info=True)
#             msg = "The code execution timed out. Please check for infinite loops or inefficient code."
#             results.append({
#                 "input": test.get("input", ""),
#                 "expected_output": test.get("expected_output", []),
#                 "actual_output": [],
#                 "status": "Error",
#                 "error_message": msg
#             })
#             break

#         except requests.exceptions.HTTPError as http_err:
#             logger.error(f"Piston API returned an HTTP error: {http_err}", exc_info=True)
#             msg = f"An error occurred with the code execution engine (HTTP {http_err.response.status_code})."
#             results.append({
#                 "input": test.get("input", ""),
#                 "expected_output": test.get("expected_output", []),
#                 "actual_output": [],
#                 "status": "Error",
#                 "error_message": msg
#             })
#             break

#         except requests.exceptions.RequestException as e:
#             logger.error(f"Piston API request failed: {e}", exc_info=True)
#             msg = "Could not connect to the code execution engine. Please try again later."
#             results.append({
#                 "input": test.get("input", ""),
#                 "expected_output": test.get("expected_output", []),
#                 "actual_output": [],
#                 "status": "Error",
#                 "error_message": msg
#             })
#             break

#     return results, error_output

def home(request):
    # If the user is authenticated, redirect them to the dashboard.
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # If not authenticated, render the new welcome page.
    return render(request, 'codingapp/welcome.html') # <--- NEW TARGET TEMPLATE

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Submission, UserProfile  # Adjust import path as needed

@login_required
def user_dashboard(request):
    # Get the user's submissions
    subs = Submission.objects.filter(user=request.user).order_by('-submitted_at')
    accepted = subs.filter(status="Accepted").count()
    rejected = subs.filter(status="Rejected").count()
    
    # Get the user's profile
    # If you are sure every user has a UserProfile, you can use request.user.userprofile
    # Otherwise, use get_object_or_404 or handle DoesNotExist
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = None  # Or handle as you wish

    return render(request, 'codingapp/dashboard.html', {
        'user_submissions': subs,
        'accepted_count': accepted,
        'rejected_count': rejected,
        'profile': profile,
        'user': request.user,  # Optional, for convenience in template
    })

from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import RegistrationForm
from .models import UserProfile

def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()

            # FIX: Don't use user.profile → use get_or_create
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.save()

            login(request, user)
            return redirect("dashboard")
    else:
        form = RegistrationForm()
    return render(request, "registration/register.html", {"form": form})


from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import Module, Submission, Question
from .forms import ModuleForm, QuestionForm

@login_required
def module_list(request):
    if request.user.is_staff:
        mods = Module.objects.all()
    else:
        user_groups = request.user.custom_groups.all()
        mods = Module.objects.filter(groups__in=user_groups).distinct()
    return render(request, 'codingapp/module_list.html', {'modules': mods})


from .models import ModuleCompletion  # make sure this is imported

@login_required
def module_detail(request, module_id):
    module = get_object_or_404(Module, id=module_id)

    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not module.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)

    questions = module.questions.all()
    total_count = questions.count()

    completed_count = Submission.objects.filter(
        user=request.user,
        question__in=questions,
        status="Accepted"
    ).values("question").distinct().count()

    # ✅ Check if already marked as completed
    is_completed = ModuleCompletion.objects.filter(
        user=request.user,
        module=module
    ).exists()

    return render(request, "codingapp/module_detail.html", {
        "module": module,
        "total_count": total_count,
        "completed_count": completed_count,
        "is_completed": is_completed,  # ✅ Add to context
    })


@staff_member_required
def add_module(request):
    form = ModuleForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect("module_list")
    return render(request, "codingapp/module_form.html", {"form": form})

@staff_member_required
def edit_module(request, module_id):
    mod = get_object_or_404(Module, id=module_id)
    form = ModuleForm(request.POST or None, instance=mod)
    if form.is_valid():
        form.save()
        return redirect("module_list")
    return render(request, "codingapp/module_form.html", {"form": form})

@staff_member_required
def delete_module(request, module_id):
    mod = get_object_or_404(Module, id=module_id)
    if request.method == "POST":
        mod.delete()
        return redirect("module_list")
    return render(request, "codingapp/module_confirm_delete.html", {"module": mod})

@login_required
def question_list(request):
    if request.user.is_staff:
        qs = Question.objects.filter(question_type="coding")
    else:
        user_groups = request.user.custom_groups.all()
        modules = Module.objects.filter(groups__in=user_groups).distinct()
        qs = Question.objects.filter(module__in=modules).distinct()
    return render(request, 'codingapp/question_list.html', {'questions': qs})


@login_required
def question_detail(request, pk):
    from celery.result import AsyncResult
    import json
    from django.conf import settings

    q = get_object_or_404(Question, pk=pk)

    # --- Access control ---
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not q.module or not q.module.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)

    # -------------------------
    # Initialize variables
    # -------------------------
    results = None
    error = None

    # --- Determine currently selected language ---
    if request.method == "POST":
        selected_lang = request.POST.get("language", "python")
    else:
        selected_lang = request.session.get(f'last_language_{pk}', request.session.get(f'language_{pk}', 'python'))

    # Session key patterns (store separately for each language)
    session_code_key = f'code_{pk}_{selected_lang}'
    session_task_key = f'submission_task_id_{pk}_{selected_lang}'

    # Load existing task/code from session (if any)
    task_id = request.session.get(session_task_key)
    code = request.session.get(session_code_key, '')

    # -------------------------
    # 1️⃣ Handle Submission (POST)
    # -------------------------
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        lang = request.POST.get("language", "python")

        if not code:
            messages.error(request, "Code cannot be empty.")
        else:
            # ⭐ Run async submission
            task = process_practice_submission.delay(request.user.id, q.id, code, lang)

            # Save per-language info in session
            request.session[f'submission_task_id_{pk}_{lang}'] = task.id
            request.session[f'code_{pk}_{lang}'] = code
            request.session[f'last_language_{pk}'] = lang
            request.session[f'language_{pk}'] = lang
            request.session.modified = True

            messages.info(request, "Your code is being processed in the background. Please wait or check back shortly.")
            return redirect('question_detail', pk=pk)

    # -------------------------
    # 2️⃣ Handle async task status (GET)
    # -------------------------
    if task_id:
        task_result = AsyncResult(task_id)

        if task_result.ready():
            # Remove task marker once finished
            request.session.pop(session_task_key, None)
            request.session.modified = True

            # Fetch last DB submission for this language
            latest_submission = Submission.objects.filter(
                user=request.user,
                question=q,
                language=selected_lang
            ).order_by('-submitted_at').first()

            if latest_submission:
                try:
                    results = json.loads(latest_submission.output) if latest_submission.output else None
                except json.JSONDecodeError:
                    results = None

                if latest_submission.status == "Accepted":
                    messages.success(request, "✅ Code Accepted! All test cases passed.")
                elif latest_submission.status == "Error":
                    messages.error(request, f"❌ Code Execution Error: {latest_submission.error}")
                    error = latest_submission.error
                else:
                    messages.warning(request, "⚠️ Some test cases failed. Try again.")
            task_id = None

        else:
            messages.info(request, f"Submission is processing... Status: {task_result.status}")

    # -------------------------
    # 3️⃣ Load code if not in session
    # -------------------------
    if not code:
        last_submission = Submission.objects.filter(
            user=request.user,
            question=q,
            language=selected_lang
        ).order_by('-submitted_at').first()

        if last_submission:
            code = last_submission.code
            if not results and last_submission.output:
                try:
                    results = json.loads(last_submission.output)
                except json.JSONDecodeError:
                    pass

    # -------------------------
    # 4️⃣ Build user_submissions map (for all languages)
    # -------------------------
    # Collect DB submissions
    db_codes = {
        s.language: s.code
        for s in Submission.objects.filter(user=request.user, question=q)
    }

    # Merge with session codes (to include unsaved async submissions)
    session_codes = {}
    for key, val in request.session.items():
        if key.startswith(f'code_{pk}_'):
            lang_name = key.split(f'code_{pk}_', 1)[1]
            session_codes[lang_name] = val

    user_submissions = {**db_codes, **session_codes}

    # -------------------------
    # 5️⃣ Prepare context and render
    # -------------------------
    context = {
        "question": q,
        "code": code,
        "selected_language": selected_lang,
        "results": results,
        "error": error,
        "task_id": task_id,
        "supported_languages": settings.SUPPORTED_LANGUAGES,
        "user_submissions": user_submissions,
    }

    return render(request, "codingapp/question_detail.html", context)


from django.views.decorators.http import require_POST
from .models import Module, ModuleCompletion, Submission
from django.contrib import messages

@login_required
@require_POST
def mark_module_completed(request, module_id):
    module = get_object_or_404(Module, id=module_id)

    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not module.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)

    questions = module.questions.all()
    total_questions = questions.count()

    completed_questions = Submission.objects.filter(
        user=request.user,
        question__in=questions,
        status='Accepted'
    ).values('question').distinct().count()

    if total_questions > 0 and completed_questions == total_questions:
        # Only create if not already marked
        ModuleCompletion.objects.get_or_create(user=request.user, module=module)
        messages.success(request, "Module marked as completed!")
    else:
        messages.error(request, "You must complete all questions (Accepted) before marking as completed.")

    return redirect('module_detail', module_id=module.id)



from .forms import QuestionForm, TestCaseForm
from django.forms import formset_factory
from django.contrib.admin.views.decorators import staff_member_required
@staff_member_required
def add_question_to_module(request, module_id):
    mod = get_object_or_404(Module, id=module_id)
    TestCaseFormSet = formset_factory(TestCaseForm, extra=1, can_delete=True)
    if request.method == "POST":
        form = QuestionForm(request.POST)
        formset = TestCaseFormSet(request.POST, prefix='testcases')
        if form.is_valid() and (form.cleaned_data['question_type'] != 'coding' or formset.is_valid()):
            q = form.save(commit=False)
            q.module = mod
            if form.cleaned_data['question_type'] == 'coding':
                test_cases = []
                for f in formset.cleaned_data:
                    if f and not f.get('DELETE', False):
                        test_cases.append({
                            'input': f['input'],
                            'expected_output': [line.strip() for line in f['expected_output'].splitlines() if line.strip()],
                        })
                if not test_cases:
                    # Validation: At least one test case required
                    formset.non_form_errors = ["At least one test case is required for coding questions."]
                    return render(request, 'codingapp/add_question.html', {
                        'form': form, 'formset': formset, 'module': mod,
                    })
                q.test_cases = test_cases
            else:
                q.test_cases = []
            q.save()
            return redirect('module_detail', module_id=mod.id)
    else:
        form = QuestionForm()
        formset = TestCaseFormSet(prefix='testcases')
    return render(request, 'codingapp/add_question.html', {
        'form': form,
        'formset': formset,
        'module': mod,
    })


def leaderboard(request):
    top = (User.objects
           .annotate(accepted_count=Count('submission', filter=Q(submission__status="Accepted")))
           .filter(accepted_count__gt=0)
           .order_by('-accepted_count'))
    return render(request, "codingapp/leaderboard.html", {"top_users": top})

from django.utils import timezone

@login_required
def assessment_list(request):
    now = timezone.now()
    if request.user.is_staff:
        asses = Assessment.objects.filter(end_time__gte=now)
    else:
        user_groups = request.user.custom_groups.all()
        asses = Assessment.objects.filter(end_time__gte=now, groups__in=user_groups).distinct()
    return render(request, 'codingapp/assessment_list.html', {"assessments": asses})

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from .models import Assessment, AssessmentSession, AssessmentQuestion

@login_required
def assessment_detail(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    # Basic permission and active checks
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not assessment.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)
    if not assessment.is_active():
        messages.warning(request, "This assessment is not active.")
        return redirect("assessment_list")

    # Get or create the session
    session, created = AssessmentSession.objects.get_or_create(
        user=request.user,
        assessment=assessment,
        defaults={"start_time": timezone.now()}
    )

    # --- FIX: Check if the user has already finished the assessment ---
    if session.end_time:
        messages.info(request, "You have already completed this assessment.")
        return redirect('assessment_result', assessment_id=assessment.id)

    # Redirect to the quiz if it exists and hasn't been submitted
    if assessment.quiz and not session.quiz_submitted:
        return redirect('assessment_quiz', assessment_id=assessment.id)

    # If no quiz or quiz is done, redirect to the first coding question
    first_question = AssessmentQuestion.objects.filter(assessment=assessment).order_by('order').first()
    if first_question:
        return redirect('submit_assessment_code', assessment_id=assessment.id, question_id=first_question.question.id)

    # Fallback if there are no coding questions
    messages.error(request, "This assessment has no coding questions.")
    return redirect('assessment_list')


@login_required
def assessment_quiz(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    session = get_object_or_404(AssessmentSession, user=request.user, assessment=assessment)
    quiz = assessment.quiz

    if session.quiz_submitted:
        # If the quiz is already done, redirect to the main assessment handler
        return redirect('assessment_detail', assessment_id=assessment.id)

    # --- FIX STARTS HERE ---
    # 1. Calculate the assessment's deadline to pass to the template's timer
    deadline = session.start_time + timezone.timedelta(minutes=assessment.duration_minutes)
    
    # 2. Prepare the list of coding questions for the navigation bar
    # This ensures the nav bar is visible even on the quiz page for a consistent UI
    all_coding_questions = AssessmentQuestion.objects.filter(assessment=assessment).select_related('question').order_by('order')
    nav_questions_data = []
    for aq in all_coding_questions:
        # At the quiz stage, no coding questions have been attempted or solved yet
        nav_questions_data.append({
            'question': aq.question,
            'is_solved': False,
            'is_attempted': False,
        })
    # --- FIX ENDS HERE ---

    # Handle the quiz logic
    questions = list(quiz.questions.all())
    import random
    random.shuffle(questions)

    if request.method == 'POST':
        submission = QuizSubmission.objects.create(user=request.user, quiz=quiz)
        score = 0
        for q in questions:
            selected = request.POST.get(f'question_{q.id}')
            if selected:
                QuizAnswer.objects.create(submission=submission, question=q, selected_option=selected)
                if selected == q.correct_answer:
                    score += 1
        submission.score = score
        submission.save()
        
        session.quiz_submitted = True
        session.save()
        
        messages.success(request, f"Quiz submitted! Your score: {score}/{len(questions)}. The coding section is now unlocked.")
        return redirect('assessment_detail', assessment_id=assessment.id)

    # 3. Add the new data to the context dictionary
    context = {
        'assessment': assessment,
        'quiz': quiz,
        'questions': questions,
        'end_time': deadline.isoformat(),      # This fixes the timer
        'all_questions': nav_questions_data,  # This provides data for the nav bar
        'focus_mode': True,  # 👈 ADD THIS LINE
    }
    
    return render(request, 'codingapp/assessment_quiz.html', context)

@login_required
def assessment_leaderboard_list(request):
    """
    Displays a list of all assessments for which a leaderboard can be viewed.
    """
    if request.user.is_staff:
        # Staff can see leaderboards for all assessments
        assessments = Assessment.objects.all().order_by('-end_time')
    else:
        # Students can see leaderboards for assessments in their groups
        user_groups = request.user.custom_groups.all()
        assessments = Assessment.objects.filter(groups__in=user_groups).distinct().order_by('-end_time')
    
    context = {
        'assessments': assessments
    }
    return render(request, 'codingapp/assessment_leaderboard_list.html', context)

@login_required
def assessment_leaderboard(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)

    # Permission Check
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not assessment.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)

    # Get all users who are assigned to the assessment's groups
    participant_ids = assessment.groups.prefetch_related('students').values_list('students', flat=True).distinct()
    participants = User.objects.filter(id__in=participant_ids)

    # Get all coding scores for this assessment, summed up per user
    coding_scores = AssessmentSubmission.objects.filter(
        assessment=assessment
    ).values('user__id').annotate(total_coding_score=Sum('score'))
    
    # Create a dictionary for fast lookup: {user_id: coding_score}
    coding_scores_dict = {item['user__id']: item['total_coding_score'] for item in coding_scores}

    # Get all quiz scores if the assessment has a quiz
    quiz_scores_dict = {}
    if assessment.quiz:
        quiz_scores = QuizSubmission.objects.filter(
            quiz=assessment.quiz
        ).values('user__id', 'score')
        quiz_scores_dict = {item['user__id']: item['score'] for item in quiz_scores}
    
    # NEW: Fetch assessment sessions for time calculation
    sessions = AssessmentSession.objects.filter(
        assessment=assessment, user__in=participants, end_time__isnull=False
    ).select_related('user')
    
    session_times_dict = {}
    for session in sessions:
        if session.end_time and session.start_time:
            # Calculate duration (timedelta)
            duration = session.end_time - session.start_time
            # Format duration into human-readable string
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            time_str = f"{hours}h {minutes}m {seconds}s"
            # Use total seconds as a sort key
            session_times_dict[session.user_id] = {'duration': duration, 'time_str': time_str, 'sort_key': total_seconds}
        else:
             session_times_dict[session.user_id] = {'duration': None, 'time_str': "N/A", 'sort_key': float('inf')}


    # Combine the scores and times for every participant
    leaderboard_data = []
    for user in participants:
        quiz_score = quiz_scores_dict.get(user.id, 0)
        coding_score = coding_scores_dict.get(user.id, 0)
        total_score = quiz_score + coding_score
        
        time_info = session_times_dict.get(user.id, {'duration': None, 'time_str': "N/A", 'sort_key': float('inf')})
        
        # Only include users who have scored something or have an attempted time
        if total_score > 0 or time_info['duration'] is not None:
             leaderboard_data.append({
                'username': user.username,
                'quiz_score': quiz_score,
                'coding_score': coding_score,
                'total_score': total_score,
                'time_taken_str': time_info['time_str'],
                'time_taken_seconds': time_info['sort_key'],
             })

    # Sort the final list by total score (desc) then time taken (asc)
    leaderboard_data.sort(key=lambda x: (-x['total_score'], x['time_taken_seconds']))


    context = {
        "assessment": assessment,
        "leaderboard": leaderboard_data
    }
    return render(request, "codingapp/assessment_leaderboard.html", context)


from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib.auth.decorators import login_required

@login_required
def submit_assessment_code(request, assessment_id, question_id):
    # kept local imports (as in your style)
    from celery.result import AsyncResult
    import json
    from django.conf import settings
    from django.db.models import Max

    assessment = get_object_or_404(Assessment, id=assessment_id)
    current_question_obj = get_object_or_404(Question, id=question_id)

    # ✅ Permission check (unchanged)
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not assessment.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)

    session = get_object_or_404(AssessmentSession, user=request.user, assessment=assessment)

    if assessment.quiz and not session.quiz_submitted:
        messages.error(request, "You must complete the quiz section before accessing coding questions.")
        return redirect('assessment_detail', assessment_id=assessment.id)

    # Timing logic
    deadline = session.start_time + timezone.timedelta(minutes=assessment.duration_minutes)
    read_only = timezone.now() > deadline

    # ===============================
    # Multi-language setup
    # ===============================
    # Determine selected language (POST wins, else session fallback)
    if request.method == "POST":
        selected_lang = request.POST.get("language", "python")
    else:
        selected_lang = request.session.get(
            f'assessment_lang_{assessment_id}_{question_id}',
            'python'
        )

    # Define per-language session keys
    session_code_key = f'assessment_code_{assessment_id}_{question_id}_{selected_lang}'
    session_task_key = f'assessment_task_id_{assessment_id}_{question_id}_{selected_lang}'

    # Load current task/code if available
    task_id = request.session.get(session_task_key)
    code = request.session.get(session_code_key, '')

    submission_results = None
    latest_submission = None

    # ===============================
    # 1️⃣ Handle POST (submission)
    # ===============================
    if request.method == "POST" and not read_only:
        code = request.POST.get("code", "").strip()
        lang = request.POST.get("language", "python")

        if not code:
            messages.error(request, "Code cannot be empty.")
        else:
            # ⭐ Async submission
            task = process_assessment_submission.delay(
                request.user.id, assessment.id, current_question_obj.id, code, lang
            )

            # Store per-language info in session (so switching languages restores quickly)
            request.session[f'assessment_task_id_{assessment_id}_{question_id}_{lang}'] = task.id
            request.session[f'assessment_code_{assessment_id}_{question_id}_{lang}'] = code
            request.session[f'assessment_lang_{assessment_id}_{question_id}'] = lang
            request.session.modified = True

            messages.info(request, "Submission is being processed in the background.")
            return redirect('submit_assessment_code', assessment_id=assessment.id, question_id=question_id)

    # ===============================
    # 2️⃣ Handle GET (status + results)
    # ===============================
    if task_id:
        task_result = AsyncResult(task_id)
        if task_result.ready():
            # remove session task id for this language (task finished)
            request.session.pop(session_task_key, None)
            request.session.modified = True

            # Refetch latest submission for this language
            latest_submission = AssessmentSubmission.objects.filter(
                assessment=assessment,
                question=current_question_obj,
                user=request.user,
                language=selected_lang
            ).order_by('-submitted_at').first()

            if latest_submission and latest_submission.output:
                try:
                    submission_results = json.loads(latest_submission.output)
                except json.JSONDecodeError:
                    submission_results = None

                if latest_submission.score == len(current_question_obj.test_cases):
                    messages.success(request, "✅ Code Accepted! All test cases passed.")
                elif latest_submission.error:
                    messages.error(request, f"❌ Code Execution Error: {latest_submission.error}")
                else:
                    messages.warning(request, "⚠️ Some test cases failed.")
        else:
            messages.info(request, f"Submission is processing... Status: {task_result.status}")

    # ===============================
    # 3️⃣ Load latest code for editor (session-first, then DB filtered by language)
    # ===============================
    if not code:
        latest_submission = AssessmentSubmission.objects.filter(
            assessment=assessment,
            question=current_question_obj,
            user=request.user,
            language=selected_lang
        ).order_by('-submitted_at').first()

        if latest_submission:
            code = latest_submission.code
            if latest_submission.output and not submission_results:
                try:
                    submission_results = json.loads(latest_submission.output)
                except json.JSONDecodeError:
                    pass

    # ===============================
    # 4️⃣ Determine read-only state (robust)
    #    lock if either deadline passed OR user has full score in ANY language
    # ===============================
    # Get best score across all languages for this user/question
    best_score_agg = AssessmentSubmission.objects.filter(
        assessment=assessment,
        question=current_question_obj,
        user=request.user
    ).aggregate(best=Max('score'))
    best_score = (best_score_agg.get('best') or 0)

    is_fully_solved = (best_score == len(current_question_obj.test_cases))
    final_read_only = read_only or is_fully_solved

    # ===============================
    # 5️⃣ Build user_submissions map (DB + session) so language switching restores instantly
    # ===============================
    db_codes = {
        s.language: s.code
        for s in AssessmentSubmission.objects.filter(
            user=request.user,
            assessment=assessment,
            question=current_question_obj
        )
    }

    session_codes = {}
    prefix = f'assessment_code_{assessment_id}_{question_id}_'
    for key, val in request.session.items():
        if key.startswith(prefix):
            lang_name = key[len(prefix):]
            session_codes[lang_name] = val

    user_submissions = {**db_codes, **session_codes}

    # ===============================
    # 6️⃣ Navigation Bar
    # ===============================
    all_qs = AssessmentQuestion.objects.filter(assessment=assessment).select_related('question').order_by('order')
    nav_questions = []
    for aq in all_qs:
        sub = AssessmentSubmission.objects.filter(
            assessment=assessment, question=aq.question, user=request.user
        ).first()
        is_solved = sub and sub.score == len(aq.question.test_cases)
        is_attempted = sub is not None
        nav_questions.append({
            'question': aq.question,
            'is_solved': is_solved,
            'is_attempted': is_attempted,
        })

    # ===============================
    # 7️⃣ Render Context
    # ===============================
    context = {
        "assessment": assessment,
        "question": current_question_obj,
        "code": code,
        "selected_language": selected_lang,
        "supported_languages": settings.SUPPORTED_LANGUAGES,
        "read_only": final_read_only,
        "end_time": deadline.isoformat(),
        "all_questions": nav_questions,
        "results": submission_results,
        "task_id": task_id,
        "focus_mode": True,
        "user_submissions": user_submissions,
    }

    return render(request, "codingapp/submit_assessment_code.html", context)

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test
from .models import Module
from .forms import ModuleForm

def is_teacher(user):
    return user.is_staff or user.groups.filter(name="Teachers").exists()

@user_passes_test(is_teacher)
def teacher_module_list(request):
    modules = Module.objects.all()
    return render(request, 'codingapp/teacher_module_list.html', {'modules': modules})

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.forms import inlineformset_factory
from .models import Module, Question
from .forms import ModuleForm, QuestionForm

@staff_member_required
def teacher_add_module(request):
    # Inline formset for questions (no instance yet, so use 'None')
    QuestionFormSet = inlineformset_factory(
        Module,
        Question,
        form=QuestionForm,
        extra=2,         # Show 2 blank forms for adding new questions
        can_delete=True  # Allow deleting questions (for inlines that are left blank)
    )

    if request.method == "POST":
        form = ModuleForm(request.POST)
        formset = QuestionFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            module = form.save()
            # Assign the module to each question before saving
            questions = formset.save(commit=False)
            for question in questions:
                question.module = module
                question.save()
            # Handle deletions
            for obj in formset.deleted_objects:
                obj.delete()
            return redirect("module_list")  # Change to your module list URL name
    else:
        form = ModuleForm()
        formset = QuestionFormSet()

    return render(request, "codingapp/teacher_module_form.html", {
        "form": form,
        "formset": formset,
    })

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.forms import inlineformset_factory
from .models import Module, Question
from .forms import ModuleForm, QuestionForm

@staff_member_required
def teacher_edit_module(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    
    # Inline formset for questions related to this module
    QuestionFormSet = inlineformset_factory(
        Module,
        Question,
        form=QuestionForm,
        extra=1,         # Show 1 blank form for adding a new question
        can_delete=True  # Allow deleting questions
    )
    
    if request.method == "POST":
        form = ModuleForm(request.POST, instance=module)
        formset = QuestionFormSet(request.POST, instance=module)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect("module_list")  # Change to your module list URL name
    else:
        form = ModuleForm(instance=module)
        formset = QuestionFormSet(instance=module)
    
    return render(request, "codingapp/teacher_module_form.html", {
        "form": form,
        "formset": formset,
        "module": module,
    })

@user_passes_test(is_teacher)
def teacher_delete_module(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    if request.method == "POST":
        module.delete()
        return redirect('teacher_module_list')
    return render(request, 'codingapp/teacher_module_confirm_delete.html', {'module': module})

@user_passes_test(is_teacher)
def teacher_dashboard(request):
    # You can add stats, recent activity, etc.
    return render(request, 'codingapp/teacher_dashboard.html')

from .models import Question
from .forms import QuestionForm

@user_passes_test(is_teacher)
def teacher_question_list(request):
    questions = Question.objects.filter()
    return render(request, 'codingapp/teacher_question_list.html', {'questions': questions})


from .forms import QuestionForm, TestCaseFormSet

from .forms import QuestionForm, TestCaseFormSet
from .models import Question
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404

@staff_member_required
def teacher_question_form(request, question_id=None):
    question = get_object_or_404(Question, id=question_id) if question_id else None

    if request.method == "POST":
        form = QuestionForm(request.POST, instance=question)
        formset = TestCaseFormSet(request.POST, prefix='testcases')
        if form.is_valid():
            q = form.save(commit=False)
            if form.cleaned_data.get('question_type') == "coding":
                if formset.is_valid():
                    tc_list = []
                    for f in formset.cleaned_data:
                        if f and not f.get('DELETE', False) and f.get('input') and f.get('expected_output'):
                            tc_list.append({
                                'input': f['input'],
                                'expected_output': [line.strip() for line in f['expected_output'].splitlines() if line.strip()],
                            })
                    q.test_cases = tc_list
                else:
                    # show errors
                    return render(request, "codingapp/teacher_question_form.html", {
                        "form": form, "formset": formset, "question": question, "action": "Edit" if question_id else "Add"
                    })
            q.save()
            form.save_m2m()
            return redirect("teacher_question_list")
    else:
        form = QuestionForm(instance=question)
        # Only for edit, prefill test cases for coding questions
        initial_test_cases = []
        if question and question.question_type == "coding":
            for tc in (question.test_cases or []):
                initial_test_cases.append({
                    'input': tc['input'],
                    'expected_output': "\n".join(tc['expected_output']),
                })
        formset = TestCaseFormSet(initial=initial_test_cases, prefix='testcases')

    return render(request, "codingapp/teacher_question_form.html", {
        "form": form,
        "formset": formset,
        "question": question,
        "action": "Edit" if question_id else "Add"
    })


@user_passes_test(is_teacher)
def teacher_delete_question(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    if request.method == "POST":
        question.delete()
        return redirect('teacher_question_list')
    return render(request, 'codingapp/teacher_question_confirm_delete.html', {'question': question})

from .models import Assessment
from .forms import AssessmentForm  # You'll need to create this form

@user_passes_test(is_teacher)
def teacher_assessment_list(request):
    assessments = Assessment.objects.all()
    return render(request, 'codingapp/teacher_assessment_list.html', {'assessments': assessments})

from .forms import AssessmentForm  # Ensure AssessmentForm is imported
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from .models import Assessment, AssessmentQuestion # It's good practice to import models you work with

def is_teacher(user):
    return user.is_staff

@user_passes_test(is_teacher)
def teacher_add_assessment(request):
    if request.method == "POST":
        form = AssessmentForm(request.POST)
        if form.is_valid():
            # Step 1: Save the main Assessment object. This also saves simple M2M fields like 'groups'.
            assessment = form.save() 
            
            # Step 2: Manually handle the 'questions' relationship using the 'through' model.
            # This is the same logic that works correctly in your edit view.
            selected_questions = form.cleaned_data.get('questions')
            
            if selected_questions:
                for question in selected_questions:
                    AssessmentQuestion.objects.create(assessment=assessment, question=question)

            messages.success(request, 'Assessment created successfully!')
            return redirect('teacher_assessment_list')
    else:
        form = AssessmentForm()
        
    return render(request, 'codingapp/teacher_assessment_form.html', {'form': form, 'action': 'Add'})
    
@user_passes_test(is_teacher)
def teacher_edit_assessment(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    if request.method == "POST":
        form = AssessmentForm(request.POST, instance=assessment)
        if form.is_valid():
            # First, save the assessment instance and its direct M2M fields (like 'groups').
            # The 'commit=False' is not strictly needed here but is good practice if you have more complex logic.
            assessment = form.save(commit=False)
            assessment.save()
            # This saves the 'groups' field correctly.
            form.save_m2m()

            # Now, manually handle the 'questions' relationship through the intermediary model.
            selected_questions = form.cleaned_data.get('questions')

            # Clear out the old question relationships for this assessment.
            assessment.assessmentquestion_set.all().delete()

            # Create the new question relationships from the selection.
            for question in selected_questions:
                AssessmentQuestion.objects.create(assessment=assessment, question=question)

            messages.success(request, "Assessment updated successfully.")
            return redirect('teacher_assessment_list')
    else:
        # For the GET request, pre-populate the form with the currently selected questions.
        initial_data = {
            'questions': assessment.assessmentquestion_set.values_list('question_id', flat=True)
        }
        form = AssessmentForm(instance=assessment, initial=initial_data)

    return render(request, 'codingapp/teacher_assessment_form.html', {
        'form': form,
        'action': 'Edit',
        'assessment': assessment
    })
    
@user_passes_test(is_teacher)
def teacher_delete_assessment(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    if request.method == "POST":
        assessment.delete()
        return redirect('teacher_assessment_list')
    return render(request, 'codingapp/teacher_assessment_confirm_delete.html', {'assessment': assessment})

from .models import Group
from .forms import GroupForm

@user_passes_test(is_teacher)
def teacher_group_list(request):
    groups = Group.objects.all()
    return render(request, 'codingapp/teacher_group_list.html', {'groups': groups})

@user_passes_test(is_teacher)
def teacher_add_group(request):
    if request.method == "POST":
        form = GroupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('teacher_group_list')
    else:
        form = GroupForm()
    return render(request, 'codingapp/teacher_group_form.html', {'form': form, 'action': 'Add'})

@user_passes_test(is_teacher)
def teacher_edit_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.method == "POST":
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            return redirect('teacher_group_list')
    else:
        form = GroupForm(instance=group)
    return render(request, 'codingapp/teacher_group_form.html', {'form': form, 'action': 'Edit'})

@user_passes_test(is_teacher)
def teacher_delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.method == "POST":
        group.delete()
        return redirect('teacher_group_list')
    return render(request, 'codingapp/teacher_group_confirm_delete.html', {'group': group})

import openpyxl
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import user_passes_test
import openpyxl
from .models import UserProfile, Role, Department, Group


@user_passes_test(lambda u: hasattr(u, "userprofile") and u.userprofile.role and u.userprofile.role.name.lower() == "admin")
def bulk_user_upload(request):
    """
    Allows admin to upload users in bulk from an Excel file (.xlsx or .xls).
    Supports columns: username, full_name, email, password, role, department, group.
    Department is optional.
    """
    result = None

    if request.method == "POST" and request.FILES.get("excel_file"):
        excel_file = request.FILES["excel_file"]

        try:
            wb = openpyxl.load_workbook(excel_file)
            ws = wb.active
        except Exception as e:
            messages.error(request, f"Error reading Excel file: {e}")
            return redirect("admin_manage_users")

        # Expected headers (now includes optional 'department')
        headers = [str(cell.value).strip().lower() if cell.value else "" for cell in ws[1]]
        expected_headers = ["username", "full_name", "email", "password", "role", "department", "group"]

        # Validate headers (at least required ones)
        required_headers = ["username", "email", "password", "role"]
        if any(h not in headers for h in required_headers):
            messages.error(
                request,
                f"Invalid headers. Required: {', '.join(required_headers)} | "
                f"Optional: department, group"
            )
            return redirect("admin_manage_users")

        created = skipped = 0
        errors = []

        # Get index mapping for flexible column order
        col_index = {h: headers.index(h) for h in headers if h}

        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                username = str(row[col_index.get("username")]).strip() if row[col_index.get("username")] else None
                email = (row[col_index.get("email")] or "").strip()
                password = (row[col_index.get("password")] or "").strip() or "password123"
                full_name = (row[col_index.get("full_name")] or "").strip()
                role_name = (row[col_index.get("role")] or "").strip()
                dept_name = (row[col_index.get("department")] or "").strip() if "department" in col_index else ""
                group_name = (row[col_index.get("group")] or "").strip() if "group" in col_index else ""

                if not username or not email or not password:
                    errors.append(f"Row {i}: Missing required fields.")
                    continue

                if User.objects.filter(username=username).exists():
                    skipped += 1
                    continue

                user = User.objects.create_user(username=username, email=email, password=password)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.full_name = full_name

                # Assign role
                if role_name:
                    role = Role.objects.filter(name__iexact=role_name).first()
                    if role:
                        profile.role = role

                # Assign department (optional)
                if dept_name:
                    dept = Department.objects.filter(name__iexact=dept_name).first()
                    if dept:
                        profile.department = dept

                profile.save()

                # Group assignment (optional)
                if group_name:
                    group, _ = Group.objects.get_or_create(name=group_name)
                    group.students.add(user)

                created += 1

            except Exception as e:
                errors.append(f"Row {i}: {e}")

        result = {"created": created, "skipped": skipped, "errors": errors}

        if created > 0:
            messages.success(request, f"✅ {created} users added successfully. {skipped} skipped.")
        if errors:
            messages.warning(request, f"⚠️ Some rows failed: {len(errors)} issues.")
            for err in errors[:5]:  # show only top 5 errors
                messages.info(request, err)

        return redirect("admin_manage_users")

    return render(request, "codingapp/bulk_user_upload.html", {"result": result})



from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import Question, Submission

def is_admin_or_teacher(user):
    return user.is_superuser or user.groups.filter(name='Teachers').exists()

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Assessment, AssessmentSubmission, AssessmentSession

def is_admin_or_teacher(user):
    return user.is_superuser or user.groups.filter(name='Teachers').exists()

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Assessment, AssessmentSubmission, AssessmentSession

def is_admin_or_teacher(user):
    return user.is_superuser or user.groups.filter(name='Teachers').exists()

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Assessment, AssessmentSubmission, AssessmentSession

def is_admin_or_teacher(user):
    return user.is_superuser or user.groups.filter(name='Teachers').exists()

@login_required
@user_passes_test(is_admin_or_teacher)
def reset_submissions_admin(request):
    users = User.objects.all().order_by('username')
    assessments = Assessment.objects.all().order_by('title')
    selected_user = None
    selected_assessment = None

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        assessment_id = request.POST.get("assessment_id")
        selected_user = get_object_or_404(User, pk=user_id)
        selected_assessment = get_object_or_404(Assessment, pk=assessment_id)

        # Delete submissions & session
        AssessmentSubmission.objects.filter(user=selected_user, assessment=selected_assessment).delete()
        AssessmentSession.objects.filter(user=selected_user, assessment=selected_assessment).delete()
        messages.success(request, f"Reset all submissions and session for {selected_user.username} in '{selected_assessment.title}'.")
        return redirect('reset_submissions_admin')

    return render(request, 'codingapp/reset_submissions_admin.html', {
        'users': users,
        'assessments': assessments,
        'selected_user': selected_user,
        'selected_assessment': selected_assessment,
    })

from django.http import JsonResponse

def clear_splash_flag(request):
    request.session.pop('force_splash', None)
    return JsonResponse({'cleared': True})

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from .models import Question

def is_teacher(user):
    return user.is_staff or user.groups.filter(name="Teachers").exists()

@user_passes_test(is_teacher)
def teacher_bulk_upload_mcq(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            df = pd.read_excel(excel_file)
            created = 0
            for _, row in df.iterrows():
                options = [row[f'Option{i}'] for i in range(1, 5) if pd.notnull(row.get(f'Option{i}'))]
                Question.objects.create(
                    title=row['Question Text'][:200],
                    description=row.get('Description', ''),
                    question_type='mcq',
                    options=options,
                    correct_answer=row['Correct Answer'],
                )
                created += 1
            messages.success(request, f"{created} MCQ questions imported successfully!")
        except Exception as e:
            messages.error(request, f"Error processing file: {e}")
    return render(request, 'codingapp/teacher_bulk_upload_mcq.html')


from .models import Quiz, QuizSubmission, QuizAnswer
from django.utils import timezone
import random
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from .models import Quiz, QuizSubmission, QuizAnswer

@login_required
def take_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    session_key = f'quiz_{quiz_id}_question_order'

    if request.method == 'POST':
        # Retrieve shuffled order from session
        question_ids = request.session.get(session_key)
        if not question_ids:
            messages.error(request, "Session expired. Please retake the quiz.")
            return redirect('take_quiz', quiz_id=quiz.id)
        questions = list(quiz.questions.filter(id__in=question_ids))
        # Preserve order
        questions.sort(key=lambda q: question_ids.index(q.id))
        # Process answers
        submission = QuizSubmission.objects.create(user=request.user, quiz=quiz, submitted_at=timezone.now())
        score = 0
        for q in questions:
            selected = request.POST.get(f'question_{q.id}')
            if selected:
                QuizAnswer.objects.create(submission=submission, question=q, selected_option=selected)
                if selected == q.correct_answer:
                    score += 1
        submission.score = score
        submission.save()
        # Remove order from session
        del request.session[session_key]
        messages.success(request, f"You scored {score} out of {len(questions)}")
        return redirect('quiz_result', submission_id=submission.id)
    else:
        # First load: shuffle and store order in session
        questions = list(quiz.questions.all())
        random.shuffle(questions)
        request.session[session_key] = [q.id for q in questions]
    return render(request, 'codingapp/take_quiz.html', {'quiz': quiz, 'questions': questions})

from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import Quiz
from .forms import QuizForm

def is_teacher(user):
    return user.is_staff or user.groups.filter(name='Teachers').exists()

from .models import Quiz
from .forms import QuizForm
from django.contrib.auth.decorators import user_passes_test

def is_teacher(user):
    return user.is_staff or user.groups.filter(name='Teachers').exists()

@user_passes_test(is_teacher)
def teacher_quiz_list(request):
    quizzes = Quiz.objects.filter(created_by=request.user)
    return render(request, 'codingapp/teacher_quiz_list.html', {'quizzes': quizzes})

@user_passes_test(is_teacher)
def teacher_quiz_create(request):
    if request.method == "POST":
        form = QuizForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.created_by = request.user
            quiz.save()
            form.save_m2m()
            return redirect('teacher_quiz_list')
    else:
        form = QuizForm()
    return render(request, 'codingapp/teacher_quiz_form.html', {'form': form, 'action': 'Create'})

@user_passes_test(is_teacher)
def teacher_quiz_edit(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, created_by=request.user)
    if request.method == "POST":
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            return redirect('teacher_quiz_list')
    else:
        form = QuizForm(instance=quiz)
    return render(request, 'codingapp/teacher_quiz_form.html', {'form': form, 'action': 'Edit'})

@user_passes_test(is_teacher)
def teacher_quiz_delete(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, created_by=request.user)
    if request.method == "POST":
        quiz.delete()
        return redirect('teacher_quiz_list')
    return render(request, 'codingapp/teacher_quiz_confirm_delete.html', {'quiz': quiz})

@login_required
def quiz_result(request, submission_id):
    submission = get_object_or_404(QuizSubmission, id=submission_id, user=request.user)
    answers = submission.answers.select_related('question')
    return render(request, 'codingapp/quiz_result.html', {'submission': submission, 'answers': answers})

from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render, get_object_or_404
from .models import Assessment, AssessmentSession, Quiz, QuizSubmission

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Assessment, QuizSubmission

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Assessment, QuizSubmission

@login_required
def quiz_leaderboard(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    quiz = assessment.quiz  # assumes Assessment has a ForeignKey to Quiz
    submissions = QuizSubmission.objects.filter(quiz=quiz).select_related('user').order_by('-score', 'submitted_at')
    print("Quiz ID for leaderboard:", quiz.id)
    print("QuizSubmission count:", QuizSubmission.objects.filter(quiz=quiz).count())

    return render(request, 'codingapp/quiz_leaderboard.html', {
        'assessment': assessment,
        'quiz': quiz,
        'submissions': submissions,
    })

from .models import Note
from .forms import NoteForm
from django.contrib.auth.decorators import login_required


from django.db.models import Q
from .models import Note

@login_required
def notes_list(request):
    user_groups = request.user.custom_groups.all()
    notes = Note.objects.filter(
        Q(group__in=user_groups) | Q(group__isnull=True)
    ).distinct()
    return render(request, 'codingapp/notes_list.html', {'notes': notes})



@login_required
def add_note(request):
    if not request.user.is_staff:
        return redirect('notes_list')
    form = NoteForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        note = form.save(commit=False)
        note.uploaded_by = request.user
        note.save()
        return redirect('notes_list')
    return render(request, 'codingapp/add_note.html', {'form': form})

from django.shortcuts import get_object_or_404
from django.contrib import messages

@login_required
def edit_note(request, note_id):
    note = get_object_or_404(Note, id=note_id, uploaded_by=request.user)
    if request.method == 'POST':
        form = NoteForm(request.POST, request.FILES, instance=note)
        if form.is_valid():
            form.save()
            messages.success(request, "Note updated successfully.")
            return redirect('notes_list')
    else:
        form = NoteForm(instance=note)
    return render(request, 'codingapp/add_note.html', {'form': form, 'edit_mode': True})


@login_required
def delete_note(request, note_id):
    note = get_object_or_404(Note, id=note_id, uploaded_by=request.user)
    if request.method == 'POST':
        note.delete()
        messages.success(request, "Note deleted successfully.")
        return redirect('notes_list')
    return render(request, 'codingapp/confirm_delete_note.html', {'note': note})


from .models import Notice, NoticeReadStatus
from .forms import NoticeForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q


# List all notices for current user (group/for_everyone)
@login_required
def notice_list(request):
    user = request.user
    notices = Notice.objects.filter(
        Q(for_everyone=True) | Q(group__in=user.custom_groups.all())
    ).order_by('-created_at').distinct()
    # Unread set
    unread_ids = set(
        NoticeReadStatus.objects.filter(
            user=user, is_read=False, notice__in=notices
        ).values_list('notice_id', flat=True)
    )
    return render(request, "codingapp/notice_list.html", {"notices": notices, "unread_ids": unread_ids})


from django.db.models import Q

# Detail view and mark as read
@login_required
def notice_detail(request, pk):
    notice = get_object_or_404(Notice, pk=pk)
    # Only show if for group/everyone
    if not notice.for_everyone and notice.group not in request.user.custom_groups.all():
        return render(request, "codingapp/permission_denied.html", status=403)
    # Mark as read
    NoticeReadStatus.objects.get_or_create(
        user=request.user, notice=notice,
        defaults={"is_read": True, "read_at": timezone.now()}
    )
    return render(request, "codingapp/notice_detail.html", {"notice": notice})

from django.db.models import Q

# Staff: Add notice
@user_passes_test(lambda u: u.is_staff)
def add_notice(request):
    if request.method == "POST":
        form = NoticeForm(request.POST, request.FILES)
        if form.is_valid():
            notice = form.save(commit=False)
            notice.created_by = request.user
            notice.save()
            form.save_m2m()
            # Pre-create unread status for all targeted users
            users = User.objects.filter(is_active=True)
            if not notice.for_everyone:
                users = users.filter(custom_groups=notice.group)
            for user in users:
                NoticeReadStatus.objects.get_or_create(user=user, notice=notice)
            return redirect("notice_list")
    else:
        form = NoticeForm()
    return render(request, "codingapp/add_notice.html", {"form": form})

# Staff: Edit and Delete Notice (similar pattern, optional for now)
from django.contrib import messages

@user_passes_test(lambda u: u.is_staff)
def edit_notice(request, pk):
    notice = get_object_or_404(Notice, pk=pk)
    if request.method == "POST":
        form = NoticeForm(request.POST, request.FILES, instance=notice)
        if form.is_valid():
            form.save()
            messages.success(request, "Notice updated successfully.")
            return redirect("notice_detail", pk=notice.pk)
    else:
        form = NoticeForm(instance=notice)
    return render(request, "codingapp/edit_notice.html", {"form": form, "notice": notice})

@user_passes_test(lambda u: u.is_staff)
def delete_notice(request, pk):
    notice = get_object_or_404(Notice, pk=pk)
    if request.method == "POST":
        notice.delete()
        messages.success(request, "Notice deleted.")
        return redirect("notice_list")
    return render(request, "codingapp/delete_notice.html", {"notice": notice})

from .forms import UserEditForm, UserProfileEditForm
from django.contrib.auth.decorators import login_required

@login_required
def edit_profile(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == "POST":
        uform = UserEditForm(request.POST, instance=user)
        pform = UserProfileEditForm(request.POST, request.FILES, instance=profile)
        if uform.is_valid() and pform.is_valid():
            uform.save()
            pform.save()
            return redirect("dashboard")
    else:
        uform = UserEditForm(instance=user)
        pform = UserProfileEditForm(instance=profile)
    return render(request, "codingapp/edit_profile.html", {
        "uform": uform,
        "pform": pform,
    })

import openpyxl
from django.contrib.auth.decorators import user_passes_test
from .forms import BulkMCQUploadForm
from .models import Question

@user_passes_test(lambda u: u.is_staff)
def bulk_mcq_upload(request):
    result = None
    if request.method == "POST":
        form = BulkMCQUploadForm(request.POST, request.FILES)
        if form.is_valid():
            module = form.cleaned_data['module']
            excel_file = form.cleaned_data['file']
            wb = openpyxl.load_workbook(excel_file)
            ws = wb.active
            headers = [cell.value for cell in ws[1]]
            expected = ["Question Text", "Option1", "Option2", "Option3", "Option4", "Correct Answer", "Description"]
            # Header validation
            if any(h not in headers for h in expected):
                result = {"created": 0, "skipped": 0, "errors": [f"Invalid headers. Expected: {', '.join(expected)}"]}
            else:
                created = skipped = 0
                errors = []
                for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                    row_data = dict(zip(headers, row))
                    title = str(row_data.get("Question Text") or "").strip()
                    options = [str(row_data.get(f"Option{n}") or "").strip() for n in range(1, 5) if row_data.get(f"Option{n}") is not None]
                    correct_answer = str(row_data.get("Correct Answer") or "").strip()
                    description = str(row_data.get("Description") or "").strip()
                    # Validation
                    if not title or len(options) != 4 or not correct_answer:
                        errors.append(f"Row {i}: Missing question/options/correct answer.")
                        continue
                    # Answer match validation (case-insensitive, strip spaces)
                    if not any(correct_answer.strip().lower() == opt.strip().lower() for opt in options):
                        errors.append(f"Row {i}: Correct answer '{correct_answer}' not among options.")
                        continue
                    # Skip duplicate
                    if Question.objects.filter(module=module, title__iexact=title).exists():
                        skipped += 1
                        continue
                    try:
                        # Store options as JSON list
                        question = Question.objects.create(
                            module=module,
                            title=title,
                            description=description,
                            question_type="mcq",
                            options=options,
                            correct_answer=correct_answer,
                        )
                        created += 1
                    except Exception as e:
                        errors.append(f"Row {i}: {e}")
                result = {"created": created, "skipped": skipped, "errors": errors}
    else:
        form = BulkMCQUploadForm()
    return render(request, "codingapp/bulk_mcq_upload.html", {"form": form, "result": result})


from django.shortcuts import render, redirect, get_object_or_404
from .models import Course
from .forms import CourseForm, CourseContentFormSet
from django.contrib.auth.decorators import login_required, user_passes_test

def is_teacher(user):
    return user.is_staff  # or use a custom check

from django.db.models import Q
from codingapp.models import Course, Group  # ✅ Make sure this is your model
from django.contrib.auth.decorators import login_required

@login_required
def course_list(request):
    user_groups = Group.objects.filter(students=request.user)
    courses = Course.objects.filter(
        Q(is_public=True) | Q(groups__in=user_groups)
    ).distinct()
    return render(request, 'codingapp/courses/list.html', {'courses': courses})

@login_required
def course_detail(request, pk):
    course = get_object_or_404(Course, pk=pk)
    # Check access
    if not course.is_public and not course.groups.filter(id__in=request.user.group_set.values_list('id', flat=True)).exists():
        return render(request, 'codingapp/courses/denied.html')
    lang_list = ['python', 'c', 'cpp', 'java', 'javascript']
    return render(request, 'codingapp/courses/detail.html', {
        'course': course,
        'lang_list': lang_list
    })




@login_required
@user_passes_test(is_teacher)
def create_course(request):
    if request.method == 'POST':
        form = CourseForm(request.POST)
        formset = CourseContentFormSet(request.POST, prefix='contents')  # ✅ Fix: use prefix

        if form.is_valid() and formset.is_valid():
            course = form.save(commit=False)
            course.created_by = request.user
            course.save()
            form.save_m2m()
            formset.instance = course
            formset.save()
            messages.success(request, "Course created successfully.")
            return redirect('manage_courses')
        else:
            print("Form errors:", form.errors)
            print("Formset errors:", formset.errors)
            messages.error(request, "Please correct the errors.")
    else:
        form = CourseForm()
        formset = CourseContentFormSet(prefix='contents')  # ✅ Fix: use same prefix

    return render(request, 'codingapp/courses/create.html', {
        'form': form,
        'formset': formset,
    })

from django.contrib import messages

@login_required
@user_passes_test(is_teacher)
def manage_courses(request):
    courses = Course.objects.filter(created_by=request.user)
    return render(request, 'codingapp/courses/manage.html', {'courses': courses})


@login_required
@user_passes_test(is_teacher)
def edit_course(request, pk):
    course = get_object_or_404(Course, pk=pk, created_by=request.user)

    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        formset = CourseContentFormSet(request.POST, instance=course)

        print("POST KEYS:", list(request.POST.keys()))  # ✅ Debugging aid

        if form.is_valid() and formset.is_valid():
            course = form.save()
            contents = formset.save(commit=False)

            for content in contents:
                content.course = course  # ✅ Reinforce link
                content.save()

            for obj in formset.deleted_objects:
                obj.delete()

            messages.success(request, "Course updated successfully.")
            return redirect('manage_courses')
        else:
            print("Form errors:", form.errors)
            print("Formset errors:", formset.errors)
            messages.error(request, "Please correct the errors.")
    else:
        form = CourseForm(instance=course)
        formset = CourseContentFormSet(instance=course)

    return render(request, 'codingapp/courses/create.html', {
        'form': form,
        'formset': formset,
    })



@login_required
@user_passes_test(is_teacher)
def delete_course(request, pk):
    course = get_object_or_404(Course, pk=pk, created_by=request.user)
    if request.method == 'POST':
        course.delete()
        messages.success(request, "Course deleted.")
        return redirect('manage_courses')
    return render(request, 'codingapp/courses/delete_confirm.html', {'course': course})

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.files.storage import default_storage

@csrf_exempt
def ckeditor_upload(request):
    if request.method == "POST" and request.FILES.get("upload"):
        file = request.FILES["upload"]
        file_path = default_storage.save(f"ckeditor_uploads/{file.name}", file)
        file_url = default_storage.url(file_path)
        return JsonResponse({
            "url": file_url
        })
    return JsonResponse({"error": "Invalid upload"}, status=400)


from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
import json, requests

@csrf_exempt
@login_required
def run_code_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            code = data.get("code", "")
            language = data.get("language", "python")
            stdin = data.get("stdin", "")  # ✅ Custom input from user

            if not code or not language:
                return JsonResponse({"error": "Missing code or language."}, status=400)

            payload = {
                "language": language,
                "version": "*",
                "files": [{"name": "main", "content": code}],
                "stdin": stdin  # ✅ Send custom input
            }

            response = requests.post(settings.PISTON_API_URL, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            return JsonResponse({
                "output": result.get("run", {}).get("stdout", ""),
                "error": result.get("run", {}).get("stderr", "")
            })

        except requests.exceptions.RequestException as req_err:
            return JsonResponse({"error": f"Piston API error: {str(req_err)}"}, status=502)
        except Exception as e:
            return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Only POST method allowed."}, status=405)




from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Avg
from django.shortcuts import render
from django.contrib.auth.models import User
from codingapp.models import Submission, QuizSubmission, Group, Module, ModuleCompletion

@login_required
@user_passes_test(lambda u: u.is_staff)
def student_performance_list(request):
    selected_group_id = request.GET.get('group')
    search_query = request.GET.get('q', '')
    sort_key = request.GET.get('sort', 'username')

    students = User.objects.filter(is_staff=False)
    if selected_group_id:
        students = students.filter(groups__id=selected_group_id)
    if search_query:
        students = students.filter(username__icontains=search_query)

    total_modules = Module.objects.count()
    performance_data = []

    for student in students:
        coding_submissions = Submission.objects.filter(user=student)
        quiz_submissions = QuizSubmission.objects.filter(user=student)

        total_coding = coding_submissions.count()
        accepted_coding = coding_submissions.filter(status='Accepted').count()
        total_quizzes = quiz_submissions.count()
        avg_quiz_score = quiz_submissions.aggregate(avg=Avg('score'))['avg'] or 0

        # ✅ Correct usage for completed modules
        completed_modules = ModuleCompletion.objects.filter(user=student, completed=True).count()

        performance_data.append({
            'student': student,
            'total_coding': total_coding,
            'accepted_coding': accepted_coding,
            'total_quizzes': total_quizzes,
            'avg_quiz_score': round(avg_quiz_score, 2),
            'completed_modules': completed_modules,
            'total_modules': total_modules,
        })

    # ✅ Sorting
    if sort_key == 'submissions':
        performance_data.sort(key=lambda x: x['total_coding'], reverse=True)
    elif sort_key == 'accepted':
        performance_data.sort(key=lambda x: x['accepted_coding'], reverse=True)
    elif sort_key == 'quizzes':
        performance_data.sort(key=lambda x: x['total_quizzes'], reverse=True)
    elif sort_key == 'score':
        performance_data.sort(key=lambda x: x['avg_quiz_score'], reverse=True)
    elif sort_key == 'top_performer':
        performance_data.sort(
            key=lambda x: (x['accepted_coding'] + x['avg_quiz_score'] + x['completed_modules']),
            reverse=True
        )
    else:
        performance_data.sort(key=lambda x: x['student'].username.lower())

    groups = Group.objects.all()

    return render(request, 'codingapp/student_performance_list.html', {
        'performance_data': performance_data,
        'groups': groups,
        'selected_group_id': selected_group_id,
        'search_query': search_query,
        'sort_key': sort_key,
    })


from django.http import HttpResponse
from django.contrib.auth.models import User
from django.db.models import Count
from .models import Submission, QuizSubmission, Module
from django.contrib.auth.decorators import login_required, user_passes_test

def is_teacher(user):
    return user.is_staff or user.groups.filter(name='Teachers').exists()

@login_required
@user_passes_test(is_teacher)
def student_performance_detail(request, student_id):
    try:
        student = User.objects.get(pk=student_id, is_staff=False)
    except User.DoesNotExist:
        return HttpResponse("Student not found.", status=404)

    coding_submissions = Submission.objects.filter(user=student).order_by('-submitted_at')
    quiz_submissions = QuizSubmission.objects.filter(user=student).order_by('-submitted_at')

    # Module-wise progress calculation
    module_progress = []
    for module in Module.objects.all():
        questions = module.questions.all()
        total = questions.count()
        completed = Submission.objects.filter(
            user=student,
            question__in=questions,
            status="Accepted"
        ).values("question").distinct().count()

        if total > 0:
            module_progress.append({
                "module_title": module.title,
                "completed": completed,
                "total": total,
                'remaining': total - completed
            })

    return render(request, 'codingapp/student_performance_detail.html', {
        'student': student,
        'coding_submissions': coding_submissions,
        'quiz_submissions': quiz_submissions,
        'module_progress': module_progress,
        
    })



import csv
from django.http import HttpResponse
from django.db.models import Avg

@login_required
@user_passes_test(is_teacher)
def export_student_performance(request):
    selected_group_id = request.GET.get('group')
    search_query = request.GET.get('q', '')

    students = User.objects.filter(is_staff=False)
    if selected_group_id:
        students = students.filter(groups__id=selected_group_id)
    if search_query:
        students = students.filter(username__icontains=search_query)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="student_performance.csv"'

    writer = csv.writer(response)
    writer.writerow(['Username', 'Total Coding Submissions', 'Accepted Submissions', 'Total Quizzes', 'Average Quiz Score'])

    for student in students:
        coding_submissions = Submission.objects.filter(user=student)
        quiz_submissions = QuizSubmission.objects.filter(user=student)

        total_coding = coding_submissions.count()
        accepted_coding = coding_submissions.filter(status='Accepted').count()
        total_quizzes = quiz_submissions.count()
        avg_quiz_score = quiz_submissions.aggregate(avg=Avg('score'))['avg'] or 0

        writer.writerow([
            student.username,
            total_coding,
            accepted_coding,
            total_quizzes,
            round(avg_quiz_score, 2)
        ])

    return response

@login_required
def assessment_result(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    session = get_object_or_404(AssessmentSession, user=request.user, assessment=assessment)
# --- FIX: Record the end time when the user finishes ---
    if not session.end_time:
        session.end_time = timezone.now()
        session.save()
    # Get all submissions for this assessment by the user
    submissions = AssessmentSubmission.objects.filter(user=request.user, assessment=assessment)
    total_score = sum(sub.score for sub in submissions)

    # You might want to mark the session as finished, e.g., by setting an end_time
    # session.end_time = timezone.now()
    # session.save()

    context = {
        'assessment': assessment,
        'submissions': submissions,
        'total_score': total_score,
    }
    return render(request, 'codingapp/assessment_result.html', context)

    from django.views.decorators.http import require_POST
import json

@login_required
@require_POST
def execute_code_api(request, question_id):
    """
    API endpoint to execute code via AJAX, enqueueing the task to Celery
    and returning the Task ID for polling.
    """
    try:
        # 1. Parse the incoming JSON data from the request body
        data = json.loads(request.body)
        code = data.get("code", "").strip()
        language = data.get("language", "python")

        # 2. Check for required data
        if not code or not language:
            return JsonResponse({"success": False, "error": "Missing code or language."}, status=400)

        # 3. Get the question object (needed for ID)
        # Note: We keep this synchronous call as it is fast DB query, and necessary for validation.
        question = get_object_or_404(Question, pk=question_id)
        
        # 4. ⭐ ASYNCHRONOUS CALL: Enqueue the code execution task
        # The task (process_practice_submission) handles running test cases and saving the submission.
        task = process_practice_submission.delay(request.user.id, question.id, code, language)
        
        # 5. Return the Task ID immediately. The client will use this to poll for results.
        return JsonResponse({
            "success": True,
            "task_id": task.id,
            "message": "Code submitted for background processing."
        })

    except json.JSONDecodeError:
        logger.error("JSON Decode Error in execute_code_api")
        return JsonResponse({"success": False, "error": "Invalid JSON payload."}, status=400)
    except Exception as e:
        # Catch unexpected errors (like DB errors or misconfigured imports)
        logger.error(f"Error in execute_code_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": f"An unexpected server error occurred: {str(e)}"}, status=500)

# NEW FUNCTION: Export Assessment Leaderboard to CSV

@user_passes_test(is_admin_or_teacher)
def export_assessment_leaderboard_csv(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)

    # 1. Fetch and Calculate Data (Same core logic as assessment_leaderboard)
    participant_ids = assessment.groups.prefetch_related('students').values_list('students', flat=True).distinct()
    participants = User.objects.filter(id__in=participant_ids)

    coding_scores = AssessmentSubmission.objects.filter(
        assessment=assessment
    ).values('user__id').annotate(total_coding_score=Sum('score'))
    coding_scores_dict = {item['user__id']: item['total_coding_score'] for item in coding_scores}

    quiz_scores_dict = {}
    if assessment.quiz:
        quiz_scores = QuizSubmission.objects.filter(
            quiz=assessment.quiz
        ).values('user__id', 'score')
        quiz_scores_dict = {item['user__id']: item['score'] for item in quiz_scores}

    sessions = AssessmentSession.objects.filter(
        assessment=assessment, user__in=participants, end_time__isnull=False
    ).select_related('user')
    
    session_times_dict = {}
    # 
    for session in sessions:
        if session.end_time and session.start_time:
            duration = session.end_time - session.start_time
            total_seconds = int(duration.total_seconds())
            # Time in minutes for CSV
            time_minutes = round(total_seconds / 60, 2)
            session_times_dict[session.user_id] = {'minutes': time_minutes}

    leaderboard_data = []
    # 
    for user in participants:
        quiz_score = quiz_scores_dict.get(user.id, 0)
        coding_score = coding_scores_dict.get(user.id, 0)
        total_score = quiz_score + coding_score
        
        time_minutes = session_times_dict.get(user.id, {}).get('minutes', 'N/A')
        
        # Only include users who have scored something or have a submission time
        if total_score > 0 or time_minutes != 'N/A':
            # Use total_score for sorting, time_minutes for the CSV output
            leaderboard_data.append({
                'username': user.username,
                'quiz_score': quiz_score,
                'coding_score': coding_score,
                'total_score': total_score,
                'time_taken_minutes': time_minutes,
                'sort_key': time_minutes if isinstance(time_minutes, (int, float)) else float('inf')
            })

    # Sort the final list by total score (desc) then time taken (asc) for accurate ranking
    leaderboard_data.sort(key=lambda x: (-x['total_score'], x['sort_key']))

    # 2. Configure the HTTP response for CSV download
    response = HttpResponse(content_type='text/csv')
    filename = slugify(assessment.title)
    response['Content-Disposition'] = f'attachment; filename="{filename}_leaderboard.csv"'

    # 3. Create the CSV writer object
    writer = csv.writer(response)

    # 4. Write the header row
    writer.writerow(['Rank', 'Username', 'Quiz Score', 'Coding Score', 'Total Score', 'Time Taken (Minutes)'])

    # 5. Write data rows
    for rank, entry in enumerate(leaderboard_data, 1):
        writer.writerow([
            rank,
            entry['username'],
            entry['quiz_score'],
            entry['coding_score'],
            entry['total_score'],
            entry['time_taken_minutes'],
        ])

    return response

# 👇 ADD THIS ENTIRE NEW VIEW FUNCTION
@login_required
def check_submission_status(request, task_id):
    """
    API endpoint for checking the status of a Celery task (used for polling).
    """
    task = AsyncResult(task_id)
    response_data = {
        'task_id': task_id,
        'status': task.status,
        'ready': task.ready(),
    }
    
    if task.ready():
        try:
            result = task.get(timeout=1) 
            response_data['final_status'] = result.get('final_status')
            response_data['results'] = result.get('results')
            response_data['error'] = result.get('error')
        except Exception as e:
            response_data['final_status'] = 'FAILURE'
            response_data['error'] = str(e)
            
    return JsonResponse(response_data)


# ==============================================================
# 🧩 Permissions Management View (Admin Dashboard)
# ==============================================================
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from codingapp.models import ActionPermission, Role, UserProfile
from codingapp.permissions import can_assign

@login_required
def permissions_manage(request):
    """
    Admin dashboard page to view and assign permissions.
    - Left: list of users
    - Right: selected user's permissions (inherited role perms vs custom perms)
    Supports bulk assignment of multiple custom permissions to a single user.
    """
    from codingapp.models import Role, ActionPermission, UserProfile
    import json

    profile = getattr(request.user, "userprofile", None)
    if not profile or not profile.role or profile.role.name.lower() != "admin":
        messages.error(request, "You don't have access to this page.")
        return redirect("dashboard")

    # Load everything needed
    permissions = ActionPermission.objects.all().order_by("code")
    roles = Role.objects.prefetch_related("permissions").order_by("name")
    users = (
        UserProfile.objects.select_related("role", "user")
        .prefetch_related("custom_permissions", "role__permissions")
        .order_by("role__name", "user__username")   # ✅ Added sorting by role name first
    )
    search_query = request.GET.get("search", "").strip()
    if search_query:
        users = users.filter(
            Q(user__username__icontains=search_query)
            | Q(full_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(role__name__icontains=search_query)
        )

    # Build fast lookup maps for template
    role_permission_map = {}
    custom_permission_map = {}
    combined_permission_map = {}

    for u in users:
        role_perms = list(u.role.permissions.values_list("id", flat=True)) if u.role else []
        custom_perms = list(u.custom_permissions.values_list("id", flat=True))
        role_permission_map[u.id] = role_perms
        custom_permission_map[u.id] = custom_perms
        combined_permission_map[u.id] = sorted(set(role_perms) | set(custom_perms))
    
    # Handle POST actions
    if request.method == "POST":
        action = request.POST.get("action")

        # ✅ Bulk update: replace a user’s custom permissions
        if action == "update_user_perms":
            user_id = request.POST.get("user_id")
            perm_ids = request.POST.getlist("perm_ids")
            try:
                user_profile = UserProfile.objects.get(id=user_id)
            except UserProfile.DoesNotExist:
                messages.error(request, "User not found.")
                return redirect("permissions_manage")

            try:
                perm_ids_int = [int(i) for i in perm_ids]
            except ValueError:
                perm_ids_int = []

            perms = ActionPermission.objects.filter(id__in=perm_ids_int)
            user_profile.custom_permissions.set(perms)
            user_profile.save()
            messages.success(request, f"Updated custom permissions for {user_profile.user.username}.")
            return redirect("permissions_manage")

        # ✅ Compatibility: single add/remove actions
        role_id = request.POST.get("role_id")
        perm_id = request.POST.get("perm_id")
        user_id = request.POST.get("user_id")
        single_action = request.POST.get("single_action")

        if role_id and perm_id and single_action:
            try:
                role = Role.objects.get(id=role_id)
                perm = ActionPermission.objects.get(id=perm_id)
                if single_action == "add":
                    role.permissions.add(perm)
                else:
                    role.permissions.remove(perm)
                messages.success(request, f"Permission '{perm.name}' updated for role '{role.name}'.")
            except Exception as e:
                messages.error(request, f"Error: {e}")
            return redirect("permissions_manage")

        if user_id and perm_id and single_action:
            try:
                up = UserProfile.objects.get(id=user_id)
                perm = ActionPermission.objects.get(id=perm_id)
                if single_action == "add":
                    up.custom_permissions.add(perm)
                else:
                    up.custom_permissions.remove(perm)
                messages.success(request, f"Permission '{perm.name}' updated for user '{up.user.username}'.")
            except Exception as e:
                messages.error(request, f"Error: {e}")
            return redirect("permissions_manage")

    # ✅ Serialize maps for template
    context = {
        "permissions": permissions,
        "roles": roles,
        "users": users,
        "role_permission_map": role_permission_map,
        "custom_permission_map": custom_permission_map,
        "user_permission_map": combined_permission_map,
        "role_perm_json": json.dumps(role_permission_map),
        "custom_perm_json": json.dumps(custom_permission_map),
    }
    return render(request, "dashboard/permissions_manage.html", context)

# ==============================================================
# 🧩 HOD Permission Management View
# ==============================================================
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from codingapp.models import UserProfile, ActionPermission, Role
import json

@login_required
def permissions_hod(request):
    """
    HOD permission management page — similar to admin, but scoped to HOD's department.
    Includes search functionality for easier filtering.
    """
    profile = getattr(request.user, "userprofile", None)
    if not profile or not profile.role or profile.role.name.lower() != "hod":
        messages.error(request, "You don't have access to this page.")
        return redirect("dashboard")

    # Limit scope to users in HOD’s department (excluding self)
    users = (
        UserProfile.objects.filter(
            Q(department=profile.department),
            ~Q(id=profile.id),  # exclude HOD themselves
        )
        .select_related("role", "user", "department")
        .prefetch_related("custom_permissions", "role__permissions")
        .order_by("role__name", "user__username")
    )

    # ✅ Search feature
    search_query = request.GET.get("search", "").strip()
    if search_query:
        users = users.filter(
            Q(user__username__icontains=search_query)
            | Q(full_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(role__name__icontains=search_query)
        )

    # Permissions the HOD can manage = those the HOD already has
    allowed_codes = profile.permission_codes()
    permissions = ActionPermission.objects.filter(code__in=allowed_codes).order_by("code")

    # Build maps for frontend JS
    role_permission_map, custom_permission_map, combined_permission_map = {}, {}, {}
    for u in users:
        role_perms = list(u.role.permissions.values_list("id", flat=True)) if u.role else []
        custom_perms = list(u.custom_permissions.values_list("id", flat=True))
        role_permission_map[u.id] = role_perms
        custom_permission_map[u.id] = custom_perms
        combined_permission_map[u.id] = sorted(set(role_perms) | set(custom_perms))

    # ✅ Handle permission updates (HOD can edit users in their dept)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_user_perms":
            user_id = request.POST.get("user_id")
            perm_ids = request.POST.getlist("perm_ids")

            try:
                target_user = UserProfile.objects.get(id=user_id, department=profile.department)
            except UserProfile.DoesNotExist:
                messages.error(request, "User not found or not in your department.")
                return redirect("permissions_hod")

            # Only assign permissions that the HOD also possesses
            perms = ActionPermission.objects.filter(id__in=perm_ids, code__in=allowed_codes)
            target_user.custom_permissions.set(perms)
            target_user.save()

            messages.success(
                request,
                f"Updated custom permissions for {target_user.user.username}.",
            )
            return redirect("permissions_hod")

    context = {
        "permissions": permissions,
        "users": users,
        "search_query": search_query,
        "role_perm_json": json.dumps(role_permission_map),
        "custom_perm_json": json.dumps(custom_permission_map),
    }
    return render(request, "dashboard/permissions_hod.html", context)

# ==============================================================
# 🧩 ADMIN CONTROL CENTER
# ==============================================================
from django.db.models import Count

from django.db.models import Count, Q, Prefetch
from django.contrib import messages
from django.shortcuts import render, redirect
from codingapp.models import Department, Role, ActionPermission, UserProfile


@login_required
def admin_control_center(request):
    """Admin's master control center with safe null handling."""
    profile = getattr(request.user, "userprofile", None)
    if not profile or not profile.role or profile.role.name.lower() != "admin":
        messages.error(request, "You don’t have access to this page.")
        return redirect("dashboard")

    # Prefetch safely (avoids N+1)
    roles = Role.objects.prefetch_related("permissions").order_by("name")
    permissions = ActionPermission.objects.all().order_by("code")

    # Annotate departments with member count and prefetch related HOD safely
    departments = (
        Department.objects.select_related("hod__user")
        .annotate(user_count=Count("userprofile"))
        .order_by("name")
    )

    users = (
        UserProfile.objects.select_related("role", "department", "user")
        .order_by("user__username")
    )

    # Count users by role
    role_counts = (
        UserProfile.objects.values("role__name")
        .annotate(count=Count("id"))
        .order_by("role__name")
    )

    context = {
        "roles": roles,
        "permissions": permissions,
        "departments": departments,
        "users": users,
        "role_counts": role_counts,
    }
    return render(request, "dashboard/admin_control_center.html", context)

# ==============================================================
# 🧩 ADMIN: MANAGE USERS
# ==============================================================
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from codingapp.models import Role, Department, UserProfile


@login_required
def admin_manage_users(request):
    """Admin view to manage users, grouped by department and role."""

    profile = getattr(request.user, "userprofile", None)
    if not profile or not profile.role or profile.role.name.lower() != "admin":
        messages.error(request, "Access denied.")
        return redirect("dashboard")

    # Load roles and departments
    roles = Role.objects.all().order_by("name")
    departments = Department.objects.all().order_by("name")

    # Prefetch all users with relations
    users = (
        UserProfile.objects.select_related("user", "role", "department")
        .prefetch_related("custom_permissions")
        .order_by("department__name", "role__name", "user__username")
    )

    search_query = request.GET.get("search", "").strip()

    users = (
        UserProfile.objects.select_related("user", "role", "department")
        .prefetch_related("custom_permissions")
        .order_by("department__name", "role__name", "user__username")
    )

    # ✅ Apply search filter
    if search_query:
        users = users.filter(
            Q(user__username__icontains=search_query)
            | Q(full_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(role__name__icontains=search_query)
        )


    # Group by department and role
    structured_data = []
    for dept in departments:
        dept_users = [u for u in users if u.department == dept]
        if not dept_users:
            continue

        dept_data = {"department": dept, "roles": []}
        for role_name in ["HOD", "Teacher", "Student"]:
            role_users = [
                u for u in dept_users
                if (u.role and u.role.name.lower() == role_name.lower())
            ]
            if role_users:
                dept_data["roles"].append({
                    "role_name": role_name,
                    "users": role_users
                })

        # Add unassigned users within department
        unassigned = [u for u in dept_users if not u.role]
        if unassigned:
            dept_data["roles"].append({
                "role_name": "Unassigned",
                "users": unassigned
            })

        structured_data.append(dept_data)

    # Users without department
    no_dept_users = [u for u in users if not u.department]
    if no_dept_users:
        structured_data.append({
            "department": None,
            "roles": [{"role_name": "Unassigned", "users": no_dept_users}]
        })

    # Handle form actions
    if request.method == "POST":
        action = request.POST.get("action")

        # ADD USER
        if action == "add_user":
            username = request.POST.get("username")
            email = request.POST.get("email")
            password = request.POST.get("password")
            role_id = request.POST.get("role_id")
            dept_id = request.POST.get("dept_id")

            if not username or not password:
                messages.error(request, "Username and password are required.")
                return redirect("admin_manage_users")

            if User.objects.filter(username=username).exists():
                messages.warning(request, f"User '{username}' already exists.")
                return redirect("admin_manage_users")

            user = User.objects.create_user(username=username, email=email, password=password)
            profile = UserProfile.objects.get(user=user)
            if role_id:
                profile.role = Role.objects.get(id=role_id)
            if dept_id:
                profile.department = Department.objects.get(id=dept_id)
            profile.save()

            messages.success(request, f"User '{username}' added successfully.")
            return redirect("admin_manage_users")

        # INDIVIDUAL UPDATE
        elif action == "update_user":
            user_id = request.POST.get("user_id")
            role_id = request.POST.get("role_id")
            dept_id = request.POST.get("dept_id")
            try:
                profile = UserProfile.objects.get(id=user_id)
                if role_id:
                    profile.role = Role.objects.get(id=role_id)
                if dept_id:
                    profile.department = Department.objects.get(id=dept_id)
                profile.save()
                messages.success(request, f"Updated user '{profile.user.username}'.")
            except Exception as e:
                messages.error(request, f"Error updating user: {e}")
            return redirect("admin_manage_users")

        # BULK UPDATE
        elif action == "bulk_update":
            selected_ids = request.POST.getlist("selected_users")
            role_id = request.POST.get("bulk_role")
            dept_id = request.POST.get("bulk_dept")
            if not selected_ids:
                messages.warning(request, "No users selected.")
                return redirect("admin_manage_users")

            count = 0
            for uid in selected_ids:
                try:
                    up = UserProfile.objects.get(id=uid)
                    if role_id:
                        up.role = Role.objects.get(id=role_id)
                    if dept_id:
                        up.department = Department.objects.get(id=dept_id)
                    up.save()
                    count += 1
                except Exception as e:
                    messages.error(request, f"Error updating user {uid}: {e}")
            messages.success(request, f"Bulk updated {count} users successfully.")
            return redirect("admin_manage_users")

        # TOGGLE ACTIVE
        elif action == "toggle_active":
            user_id = request.POST.get("user_id")
            try:
                profile = UserProfile.objects.get(id=user_id)
                profile.user.is_active = not profile.user.is_active
                profile.user.save()
                state = "activated" if profile.user.is_active else "deactivated"
                messages.success(request, f"User '{profile.user.username}' has been {state}.")
            except Exception as e:
                messages.error(request, f"Error toggling user: {e}")
            return redirect("admin_manage_users")

        # DELETE USER
        elif action == "delete_user":
            user_id = request.POST.get("user_id")
            try:
                profile = UserProfile.objects.get(id=user_id)
                username = profile.user.username
                profile.user.delete()
                messages.success(request, f"User '{username}' deleted successfully.")
            except Exception as e:
                messages.error(request, f"Error deleting user: {e}")
            return redirect("admin_manage_users")

        # RESET PASSWORD
        elif action == "reset_password":
            user_id = request.POST.get("user_id")
            new_password = request.POST.get("new_password")
            try:
                profile = UserProfile.objects.get(id=user_id)
                profile.user.set_password(new_password)
                profile.user.save()
                messages.success(request, f"Password reset for '{profile.user.username}'.")
            except Exception as e:
                messages.error(request, f"Error resetting password: {e}")
            return redirect("admin_manage_users")

        # BULK ACTIVATE/DEACTIVATE/DELETE
        elif action in ["bulk_activate", "bulk_deactivate", "bulk_delete"]:
            selected_ids = request.POST.getlist("selected_users")
            if not selected_ids:
                messages.warning(request, "No users selected.")
                return redirect("admin_manage_users")

            count = 0
            for uid in selected_ids:
                try:
                    up = UserProfile.objects.get(id=uid)
                    if action == "bulk_delete":
                        up.user.delete()
                    elif action == "bulk_activate":
                        up.user.is_active = True
                        up.user.save()
                    elif action == "bulk_deactivate":
                        up.user.is_active = False
                        up.user.save()
                    count += 1
                except Exception as e:
                    messages.error(request, f"Error processing user {uid}: {e}")

            verb = (
                "deleted" if action == "bulk_delete"
                else "activated" if action == "bulk_activate"
                else "deactivated"
            )
            messages.success(request, f"{count} users {verb} successfully.")
            return redirect("admin_manage_users")

    context = {
        "roles": roles,
        "departments": departments,
        "structured_data": structured_data,
    }
    return render(request, "dashboard/admin_manage_users.html", context)

@login_required
def admin_manage_departments(request):
    """Admin view to manage departments: create, edit, delete, assign HODs, with user stats."""
    from django.db.models import Count, Q
    from codingapp.models import Department, UserProfile

    # 🔒 Access control
    profile = getattr(request.user, "userprofile", None)
    if not profile or not profile.role or profile.role.name.lower() != "admin":
        messages.error(request, "Access denied.")
        return redirect("dashboard")

    # Annotate departments with teacher & student counts
    departments = (
        Department.objects.select_related("hod")
        .annotate(
            teacher_count=Count(
                "userprofile",
                filter=Q(userprofile__role__name__iexact="teacher"),
            ),
            student_count=Count(
                "userprofile",
                filter=Q(userprofile__role__name__iexact="student"),
            ),
        )
        .order_by("name")
    )

    hod_candidates = (
        UserProfile.objects.filter(role__name__iexact="hod")
        .select_related("user")
        .order_by("user__username")
    )

    # ✅ Handle actions
    if request.method == "POST":
        action = request.POST.get("action")

        # ---------- Add Department ----------
        if action == "add_department":
            name = request.POST.get("name")
            code = request.POST.get("code")
            hod_id = request.POST.get("hod_id")

            if not name or not code:
                messages.error(request, "Name and code are required.")
                return redirect("admin_manage_departments")

            dept, created = Department.objects.get_or_create(name=name, code=code)
            if hod_id:
                try:
                    hod_profile = UserProfile.objects.get(id=hod_id)
                    dept.hod = hod_profile
                except UserProfile.DoesNotExist:
                    messages.warning(request, "Invalid HOD selected.")
            dept.save()
            messages.success(
                request,
                f"Department '{name}' {'added' if created else 'updated'} successfully.",
            )
            return redirect("admin_manage_departments")

        # ---------- Update Department ----------
        elif action == "update_department":
            dept_id = request.POST.get("dept_id")
            name = request.POST.get("name")
            code = request.POST.get("code")
            hod_id = request.POST.get("hod_id")

            try:
                dept = Department.objects.get(id=dept_id)
                dept.name = name
                dept.code = code
                dept.hod = UserProfile.objects.get(id=hod_id) if hod_id else None
                dept.save()
                messages.success(request, f"Updated department '{dept.name}'.")
            except Exception as e:
                messages.error(request, f"Error updating department: {e}")
            return redirect("admin_manage_departments")

        # ---------- Delete Department ----------
        elif action == "delete_department":
            dept_id = request.POST.get("dept_id")
            try:
                dept = Department.objects.get(id=dept_id)
                name = dept.name
                dept.delete()
                messages.success(request, f"Department '{name}' deleted.")
            except Exception as e:
                messages.error(request, f"Error deleting department: {e}")
            return redirect("admin_manage_departments")

    # ---------- Context ----------
    context = {
        "departments": departments,
        "hod_candidates": hod_candidates,
    }
    return render(request, "dashboard/admin_manage_departments.html", context)

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from codingapp.models import Group, Department, UserProfile

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from codingapp.models import Group, Department, UserProfile

@login_required
def manage_groups(request):
    """Unified Manage Groups view (CRUD + Department filter + student assignment)."""

    profile = getattr(request.user, "userprofile", None)
    if not profile or not profile.role:
        messages.error(request, "Access denied. Missing role information.")
        return redirect("dashboard")

    role_name = profile.role.name.lower()

    # Permissions: only Admin, HOD, and Teacher can access
    if role_name not in ["admin", "hod", "teacher"]:
        messages.error(request, "Access denied.")
        return redirect("dashboard")

    # Determine department filter (HOD/Teacher limited to their dept)
    if role_name == "admin":
        departments = Department.objects.all().order_by("name")
        groups = Group.objects.select_related("department").prefetch_related("students").order_by("department__name", "name")
        students = UserProfile.objects.filter(role__name__iexact="student").select_related("user").order_by("user__username")
    else:
        departments = Department.objects.filter(id=profile.department_id)
        groups = Group.objects.filter(department=profile.department).select_related("department").prefetch_related("students").order_by("name")
        students = UserProfile.objects.filter(role__name__iexact="student", department=profile.department).select_related("user").order_by("user__username")

    # ---------- Handle POST actions ----------
    if request.method == "POST":
        action = request.POST.get("action")

        # ✅ Create or Edit Group
        if action == "add_or_edit_group":
            group_id = request.POST.get("group_id")
            name = request.POST.get("name", "").strip()
            dept_id = request.POST.get("department_id") or None
            student_ids = request.POST.getlist("student_ids")

            if not name:
                messages.error(request, "Group name cannot be empty.")
                return redirect("manage_groups")

            department = None
            if dept_id:
                try:
                    department = Department.objects.get(id=dept_id)
                except Department.DoesNotExist:
                    messages.error(request, "Invalid department selected.")
                    return redirect("manage_groups")

            if group_id:
                # Edit existing
                try:
                    group = Group.objects.get(id=group_id)
                    group.name = name
                    group.department = department
                    group.save()
                    # Update students
                    if student_ids:
                        group.students.set([s.user for s in UserProfile.objects.filter(id__in=student_ids)])
                    else:
                        group.students.clear()
                    messages.success(request, f"Updated group '{group.name}'.")
                except Group.DoesNotExist:
                    messages.error(request, "Group not found.")
            else:
                # Create new
                group = Group.objects.create(name=name, department=department)
                if student_ids:
                    group.students.set([s.user for s in UserProfile.objects.filter(id__in=student_ids)])
                messages.success(request, f"Group '{group.name}' created successfully.")

            return redirect("manage_groups")

        # ✅ Delete Group
        elif action == "delete_group":
            group_id = request.POST.get("group_id")
            try:
                group = Group.objects.get(id=group_id)
                name = group.name
                group.delete()
                messages.success(request, f"Group '{name}' deleted successfully.")
            except Group.DoesNotExist:
                messages.error(request, "Group not found.")
            return redirect("manage_groups")

    # ---------- Context ----------
    context = {
        "groups": groups,
        "departments": departments,
        "students": students,
    }
    return render(request, "dashboard/manage_groups.html", context)
