import requests
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Q



from .models import (
    Question, Submission, Module,
    Assessment, AssessmentQuestion, AssessmentSubmission,
    AssessmentSession
)
from .forms import ModuleForm, QuestionForm
from codingapp import models

# Piston (code execution) API endpoint
PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"
#PISTON_API_URL = "http://localhost:2000/api/v2/execute"
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

def execute_code(code, language, test_cases):
    """Helper to run code via Piston and collect results."""
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
            resp.raise_for_status()
            data = resp.json()
            stdout = data.get("run", {}).get("stdout", "").strip()
            stderr = data.get("run", {}).get("stderr", "").strip()

            # Split the stdout into lines and strip whitespace
            actual_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            expected_lines = test.get("expected_output", [])

            # Compare actual output with expected output
            if len(actual_lines) != len(expected_lines):
                status = "Rejected"
                error_message = f"Expected {len(expected_lines)} lines, got {len(actual_lines)} lines"
            else:
                # Compare each line
                mismatches = []
                for i, (actual, expected) in enumerate(zip(actual_lines, expected_lines)):
                    if actual != expected:
                        mismatches.append(f"Line {i+1}: Expected '{expected}', got '{actual}'")
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
                "expected_output": expected_lines,  # Now a list of strings
                "actual_output": actual_lines,      # Now a list of strings
                "status": status,
                "error_message": error_message if status in ["Rejected", "Error"] else ""
            })
        except requests.exceptions.RequestException as e:
            msg = f"API error: {e}"
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
    return redirect('dashboard') if request.user.is_authenticated else redirect('login')

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
            profile.birthdate = form.cleaned_data.get('birthdate')
            profile.profile_picture = form.cleaned_data.get('profile_picture')
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
                    ModuleCompletion.objects.get_or_create(student=request.user, module=q.module)
            

            # ✅ Auto mark module as completed
            if q.module:
                module_questions = q.module.questions.all()
                accepted_count = Submission.objects.filter(
                    user=request.user,
                    question__in=module_questions,
                    status="Accepted"
                ).values("question").distinct().count()

                if accepted_count == module_questions.count():
                    ModuleCompletion.objects.get_or_create(student=request.user, module=q.module)

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
        ModuleCompletion.objects.get_or_create(student=request.user, module=module)
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
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not assessment.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)
    if not assessment.is_active():
        messages.warning(request, "This assessment is not active.")
        return redirect("assessment_list")

    session, created = AssessmentSession.objects.get_or_create(
        user=request.user,
        assessment=assessment,
        defaults={"start_time": timezone.now()}
    )
    deadline = session.start_time + timezone.timedelta(minutes=assessment.duration_minutes)
    remaining_seconds = max(0, int((deadline - timezone.now()).total_seconds()))

    # --- NEW: Check for quiz section ---
    if assessment.quiz and not session.quiz_submitted:
        # Redirect to the quiz section if quiz not yet submitted
        return redirect('assessment_quiz', assessment_id=assessment.id)

    # Coding questions unlocked only after quiz is submitted (or if no quiz)
    questions = AssessmentQuestion.objects.filter(assessment=assessment).select_related('question')
    return render(request, 'codingapp/assessment_detail.html', {
        "assessment": assessment,
        "questions": questions,
        "end_time": deadline.isoformat(),
        "remaining_seconds": remaining_seconds
    })

@login_required
def assessment_quiz(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    session = get_object_or_404(AssessmentSession, user=request.user, assessment=assessment)
    quiz = assessment.quiz
    if session.quiz_submitted:
        # Already done, go to coding section
        return redirect('assessment_detail', assessment_id=assessment.id)
    questions = list(quiz.questions.all())
    import random
    random.shuffle(questions)
    if request.method == 'POST':
        # Save submission
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
        messages.success(request, f"Quiz submitted! Score: {score}/{len(questions)}. Coding section unlocked.")
        return redirect('assessment_detail', assessment_id=assessment.id)
    return render(request, 'codingapp/assessment_quiz.html', {
        'assessment': assessment,
        'quiz': quiz,
        'questions': questions,
    })


@login_required
def assessment_leaderboard(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not assessment.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)
    leaderboard = (
        AssessmentSubmission.objects
        .filter(assessment=assessment)
        .values('user__username')
        .annotate(total_score=Count('score'))
        .order_by('-total_score')
    )
    return render(request, "codingapp/assessment_leaderboard.html", {
        "assessment": assessment,
        "leaderboard": leaderboard
    })

from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib.auth.decorators import login_required

@login_required
def submit_assessment_code(request, assessment_id, question_id):
    A = get_object_or_404(Assessment, id=assessment_id)
    Qobj = get_object_or_404(Question, id=question_id)
    if not request.user.is_staff:
        user_groups = request.user.custom_groups.all()
        if not A.groups.filter(id__in=user_groups.values_list('id', flat=True)).exists():
            return render(request, "codingapp/permission_denied.html", status=403)
    try:
        sess = AssessmentSession.objects.get(user=request.user, assessment=A)
        if not sess.start_time:
            sess.start_time = timezone.now()
            sess.save()
    except AssessmentSession.DoesNotExist:
        messages.warning(request, "Please start the assessment first.")
        return redirect("assessment_list")

    # --- NEW: Lock coding questions until quiz is submitted ---
    if A.quiz and not sess.quiz_submitted:
        messages.error(request, "You must complete the quiz section before accessing coding questions.")
        return redirect('assessment_detail', assessment_id=A.id)

    deadline = sess.start_time + timezone.timedelta(minutes=A.duration_minutes)
    now = timezone.now()
    remaining_seconds = max(0, int((deadline - now).total_seconds()))
    read_only = remaining_seconds <= 0
    existing = AssessmentSubmission.objects.filter(
        assessment=A, question=Qobj, user=request.user
    ).first()
    code = existing.code if existing else ""
    lang = existing.language if existing else "python"
    results = None
    error_output = None
    score = 0
    next_q = None

    if existing and existing.score == len(Qobj.test_cases):
        # Already fully solved, lock editor
        read_only = True
        results, _ = execute_code(code, lang, Qobj.test_cases)
        score = existing.score
    elif request.method == "POST" and not read_only:
        code = request.POST.get("code", "").strip()
        lang = request.POST.get("language", "python")
        if not code:
            messages.error(request, "Code cannot be empty.")
        else:
            results, error_output = execute_code(code, lang, Qobj.test_cases)
            score = sum(1 for r in results if r["status"] == "Accepted")
            all_accepted = all(r["status"] == "Accepted" for r in results) if results else False
            if existing:
                existing.code = code
                existing.language = lang
                existing.output = "\n".join(results[0]["actual_output"]) if results else ""
                existing.error = error_output or ""
                existing.score = score
                existing.save()
            else:
                AssessmentSubmission.objects.create(
                    user=request.user, assessment=A, question=Qobj,
                    code=code, language=lang,
                    output="\n".join(results[0]["actual_output"]) if results else "",
                    error=error_output or "", score=score
                )
            if all_accepted:
                read_only = True
                messages.success(request, "All test cases passed! Question locked.")
            else:
                read_only = False
                messages.info(request, "Some test cases failed. Please try again.")

    all_qs = AssessmentQuestion.objects.filter(assessment=A).select_related('question')
    for item in all_qs:
        q2 = item.question
        if q2.id != Qobj.id:
            done = AssessmentSubmission.objects.filter(
                assessment=A, question=q2, user=request.user, score=len(q2.test_cases)
            ).exists()
            if not done:
                next_q = q2
                break

    return render(request, "codingapp/submit_assessment_code.html", {
        "assessment": A,
        "question": Qobj,
        "code": code,
        "selected_language": lang,
        "supported_languages": SUPPORTED_LANGUAGES,
        "results": results,
        "score": score,
        "read_only": read_only,
        "next_question": next_q,
        "end_time": deadline.isoformat(),
        "remaining_seconds": remaining_seconds
    })

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

@user_passes_test(is_teacher)
def teacher_edit_assessment(request, assessment_id):
    assessment = get_object_or_404(Assessment, id=assessment_id)
    if request.method == "POST":
        form = AssessmentForm(request.POST, instance=assessment)
        if form.is_valid():
            form.save()
            return redirect('teacher_assessment_list')
    else:
        form = AssessmentForm(instance=assessment)
    return render(request, 'codingapp/teacher_assessment_form.html', {'form': form, 'action': 'Edit'})

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
                            question_type="MCQ",
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

            response = requests.post("https://emkc.org/api/v2/piston/execute", json=payload, timeout=10)
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
