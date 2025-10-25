import requests
import logging
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


from .models import (
    Question, Submission, Module,
    Assessment, AssessmentQuestion, AssessmentSubmission,
    AssessmentSession
)
from .forms import ModuleForm, QuestionForm
from codingapp import models

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

def execute_code(code, language, test_cases):
    """
    Helper to run code via Piston and collect results, with improved error handling.
    """
    results = []
    error_output = None

    for test in test_cases or []:
        payload = {
            "language": language,
            "version": "*",
            "files": [{"name": "solution", "content": code}],
            "stdin": test.get("input", "")
        }

        try:
            resp = requests.post(PISTON_API_URL, json=payload, timeout=10)
            resp.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

            data = resp.json()
            stdout = data.get("run", {}).get("stdout", "").strip()
            stderr = data.get("run", {}).get("stderr", "").strip()

            actual_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            expected_lines = test.get("expected_output", [])

            if stderr:
                status = "Error"
                error_message = stderr
            elif len(actual_lines) != len(expected_lines):
                status = "Rejected"
                error_message = f"Output mismatch: Expected {len(expected_lines)} lines, but got {len(actual_lines)}."
            else:
                mismatches = [f"Line {i+1}: Expected '{expected}', got '{actual}'"
                              for i, (actual, expected) in enumerate(zip(actual_lines, expected_lines))
                              if actual != expected]
                if mismatches:
                    status = "Rejected"
                    error_message = "; ".join(mismatches)
                else:
                    status = "Accepted"
                    error_message = ""

            results.append({
                "input": test.get("input", ""),
                "expected_output": expected_lines,
                "actual_output": actual_lines,
                "status": status,
                "error_message": error_message
            })

        except requests.exceptions.Timeout:
            logger.error("Piston API request timed out.", exc_info=True)
            msg = "The code execution timed out. Please check for infinite loops or inefficient code."
            results.append({
                "input": test.get("input", ""),
                "expected_output": test.get("expected_output", []),
                "actual_output": [],
                "status": "Error",
                "error_message": msg
            })
            break

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Piston API returned an HTTP error: {http_err}", exc_info=True)
            msg = f"An error occurred with the code execution engine (HTTP {http_err.response.status_code})."
            results.append({
                "input": test.get("input", ""),
                "expected_output": test.get("expected_output", []),
                "actual_output": [],
                "status": "Error",
                "error_message": msg
            })
            break

        except requests.exceptions.RequestException as e:
            logger.error(f"Piston API request failed: {e}", exc_info=True)
            msg = "Could not connect to the code execution engine. Please try again later."
            results.append({
                "input": test.get("input", ""),
                "expected_output": test.get("expected_output", []),
                "actual_output": [],
                "status": "Error",
                "error_message": msg
            })
            break

    return results, error_output

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
    q = get_object_or_404(Question, pk=pk)

    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not q.module or not q.module.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)

    code = request.session.get(f'code_{pk}', '')
    lang = request.session.get(f'language_{pk}', 'python')
    error = stderr = results = None

    if not code:
        last = Submission.objects.filter(user=request.user, question=q).first()
        if last:
            code, lang = last.code, last.language

    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        lang = request.POST.get("language", "python")
        if not code:
            error = "Code cannot be empty"
        else:
            results, stderr = execute_code(code, lang, q.test_cases)
            sub, created = Submission.objects.get_or_create(
                user=request.user, question=q,
                defaults={'code': code, 'language': lang, 'status': 'Pending'}
            )
            sub.code = code
            sub.language = lang
            all_accepted = results and all(r["status"] == "Accepted" for r in results)
            sub.status = "Accepted" if all_accepted else "Rejected" if results else "Pending"
            sub.output = "\n".join(results[0]["actual_output"]) if results else ""
            sub.error = stderr or ""
            sub.save()
            if all_accepted and q.module:
                module_questions = q.module.questions.all()
                solved_count = Submission.objects.filter(
                    user=request.user,
                    question__in=module_questions,
                    status="Accepted"
                ).values("question").distinct().count()

                if solved_count == module_questions.count():
                    from .models import ModuleCompletion  # import at the top if needed
                    ModuleCompletion.objects.get_or_create(user=request.user, module=q.module)
            

            # ✅ Auto mark module as completed
            if q.module:
                module_questions = q.module.questions.all()
                accepted_count = Submission.objects.filter(
                    user=request.user,
                    question__in=module_questions,
                    status="Accepted"
                ).values("question").distinct().count()

                if accepted_count == module_questions.count():
                    ModuleCompletion.objects.get_or_create(user=request.user, module=q.module)

            request.session[f'code_{pk}'] = code
            request.session[f'language_{pk}'] = lang
            request.session.modified = True

            messages.success(request, "Code submitted!") if not stderr else messages.error(request, stderr)

    return render(request, "codingapp/question_detail.html", {
        "question": q,
        "code": code,
        "selected_language": lang,
        "results": results,
        "error": error,
        "error_output": stderr,
        "supported_languages": SUPPORTED_LANGUAGES, # <--- CRITICAL ADDITION
    })

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
    assessment = get_object_or_404(Assessment, id=assessment_id)
    current_question_obj = get_object_or_404(Question, id=question_id)

    # Permission checks
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not assessment.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)

    session = get_object_or_404(AssessmentSession, user=request.user, assessment=assessment)
    if assessment.quiz and not session.quiz_submitted:
        messages.error(request, "You must complete the quiz section before accessing coding questions.")
        return redirect('assessment_detail', assessment_id=assessment.id)

    deadline = session.start_time + timezone.timedelta(minutes=assessment.duration_minutes)
    read_only = timezone.now() > deadline

    # Handle POST request for new code submission
    if request.method == "POST" and not read_only:
        code = request.POST.get("code", "").strip()
        lang = request.POST.get("language", "python")
        if not code:
            messages.error(request, "Code cannot be empty.")
        else:
            results, error_output = execute_code(code, lang, current_question_obj.test_cases)
            score = sum(1 for r in results if r["status"] == "Accepted")

            AssessmentSubmission.objects.update_or_create(
                user=request.user, assessment=assessment, question=current_question_obj,
                defaults={
                    'code': code,
                    'language': lang,
                    'output': "\n".join(res["actual_output"][0] for res in results if res.get("actual_output")),
                    'error': error_output or "\n".join(res.get("error_message", "") for res in results),
                    'score': score
                }
            )
        # Redirect after POST to show results on the reloaded page
        return redirect('submit_assessment_code', assessment_id=assessment.id, question_id=question_id)

    # --- THIS IS THE FIX: Logic for GET request to show results ---
    submission_results = None
    latest_submission = AssessmentSubmission.objects.filter(
        assessment=assessment, question=current_question_obj, user=request.user
    ).first()

    if latest_submission:
        # Re-run the saved code to generate the detailed result breakdown for display
        submission_results, _ = execute_code(latest_submission.code, latest_submission.language, current_question_obj.test_cases)

    # Prepare data for rendering the template
    code = latest_submission.code if latest_submission else ""
    lang = latest_submission.language if latest_submission else "python"
    is_fully_solved = latest_submission and latest_submission.score == len(current_question_obj.test_cases)
    final_read_only = read_only or is_fully_solved

    # Prepare data for the question navigation bar
    all_qs = AssessmentQuestion.objects.filter(assessment=assessment).select_related('question').order_by('order')
    nav_questions = []
    for aq in all_qs:
        sub = AssessmentSubmission.objects.filter(assessment=assessment, question=aq.question, user=request.user).first()
        is_solved = sub and sub.score == len(aq.question.test_cases)
        is_attempted = sub is not None
        nav_questions.append({
            'question': aq.question,
            'is_solved': is_solved,
            'is_attempted': is_attempted,
        })

    context = {
        "assessment": assessment,
        "question": current_question_obj,
        "code": code,
        "selected_language": lang,
        "supported_languages": SUPPORTED_LANGUAGES,
        "read_only": final_read_only,
        "end_time": deadline.isoformat(),
        "all_questions": nav_questions,
        "results": submission_results,  # This now contains the data to display
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

@user_passes_test(is_teacher)
def teacher_add_assessment(request):
    if request.method == "POST":
        form = AssessmentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('teacher_assessment_list')
    else:
        form = AssessmentForm()
    return render(request, 'codingapp/teacher_assessment_form.html', {'form': form, 'action': 'Add'})

from .models import Assessment, AssessmentQuestion # Make sure AssessmentQuestion is imported

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

from django.contrib.auth.models import User
from .models import UserProfile, Group
from django.contrib.auth.decorators import user_passes_test
import openpyxl

@user_passes_test(lambda u: u.is_staff)
def bulk_user_upload(request):
    result = None
    if request.method == "POST" and request.FILES.get("excel_file"):
        excel_file = request.FILES["excel_file"]
        wb = openpyxl.load_workbook(excel_file)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        expected_headers = ["username", "full_name", "email", "password", "group"]
        if any(h not in headers for h in expected_headers):
            result = {"created": 0, "skipped": 0, "errors": ["Invalid headers. Expected: " + ", ".join(expected_headers)]}
        else:
            created = skipped = 0
            errors = []
            for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                row_data = dict(zip(headers, row))
                username = str(row_data.get("username")).strip() if row_data.get("username") else None
                full_name = row_data.get("full_name", "").strip()
                email = row_data.get("email", "").strip()
                password = row_data.get("password", "").strip()
                group_name = row_data.get("group", "").strip()
                if not username or not password or not email:
                    errors.append(f"Row {i}: Missing username/password/email.")
                    continue
                if User.objects.filter(username=username).exists():
                    skipped += 1
                    continue
                try:
                    user = User.objects.create_user(username=username, email=email, password=password)
                    user_profile, _ = UserProfile.objects.get_or_create(user=user)
                    user_profile.full_name = full_name
                    user_profile.save()
                    # Group assignment
                    if group_name:
                        group, _ = Group.objects.get_or_create(name=group_name)
                        group.students.add(user)
                    created += 1
                except Exception as e:
                    errors.append(f"Row {i}: {e}")
            result = {"created": created, "skipped": skipped, "errors": errors}
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
    API endpoint to execute code via AJAX without a full page reload.
    This view is designed to be called by a JavaScript client.
    """
    try:
        # 1. Parse the incoming JSON data from the request body
        data = json.loads(request.body)
        code = data.get("code", "")
        language = data.get("language", "python")

        # 2. Get the question object to access its test cases
        question = get_object_or_404(Question, pk=question_id)

        # 3. Reuse our existing, robust code execution logic
        results, error_output = execute_code(code, language, question.test_cases)

        # 4. Save the submission to the database, just like the original view
        # This ensures user progress is still tracked
        submission, _ = Submission.objects.update_or_create(
            user=request.user,
            question=question,
            defaults={
                'code': code,
                'language': language,
                'status': "Accepted" if all(r["status"] == "Accepted" for r in results) else "Rejected",
                'output': results[0]['actual_output'] if results and results[0].get('actual_output') else "",
                'error': error_output or "",
            }
        )
        
        # 5. Return the results as a JSON response
        return JsonResponse({
            "success": True,
            "results": results,
            "error_output": error_output
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error in execute_code_api: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": "An unexpected server error occurred."}, status=500)

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