import datetime
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import (AssessmentForm, BulkMCQUploadForm, CourseForm, GroupForm,
                    ModuleForm, NoteForm, NoticeForm, QuestionForm, QuizForm,
                    RegistrationForm)
from .models import (Assessment, AssessmentQuestion, AssessmentSession,
                     AssessmentSubmission, Course, Group, Module, Note,
                     Notice, Question, Quiz, QuizAnswer, QuizSubmission,
                     Submission, UserProfile)


class BaseTestCase(TestCase):
    def setUp(self):
        """
        Set up common objects for all test classes.
        """
        self.client = Client()
        self.user = User.objects.create_user(username='student', password='password', email='student@example.com')
        self.teacher = User.objects.create_user(username='teacher', password='password', is_staff=True)
        self.group = Group.objects.create(name='Test Group')
        self.group.students.add(self.user)

        self.module = Module.objects.create(title="Test Module")
        self.module.groups.add(self.group)

        self.question = Question.objects.create(
            module=self.module,
            title="Test Coding Question",
            description="A coding question for testing.",
            question_type="coding",
            test_cases=[{"input": "1", "expected_output": ["1"]}]
        )
        self.mcq_question = Question.objects.create(
            module=self.module,
            title="Test MCQ Question",
            description="An MCQ for testing.",
            question_type="mcq",
            options=["A", "B", "C", "D"],
            correct_answer="A"
        )


class AuthenticationViewTests(BaseTestCase):
    def test_register_view(self):
        """
        Test the user registration view.
        """
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/register.html')

        # Test successful registration with all required form fields
        response = self.client.post(reverse('register'), {
            'username': 'newstudent',
            'email': 'newstudent@example.com',
            'password1': 'ComplexPassword123!',
            'password2': 'ComplexPassword123!',
            'full_name': 'New Student',
        })

        # Assert that the user was created and the redirect is correct
        self.assertTrue(User.objects.filter(username='newstudent').exists())
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_view(self):
        """
        Test the user login view.
        """
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/login.html')

        # Test successful login
        response = self.client.post(reverse('login'), {
            'username': 'student',
            'password': 'password',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

    def test_invalid_login(self):
        """Test login with invalid credentials."""
        response = self.client.post(reverse('login'), {'username': 'student', 'password': 'wrongpassword'})
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], None,
                             'Please enter a correct username and password. Note that both fields may be case-sensitive.')

    def test_logout_view(self):
        """Test that a logged-in user can log out."""
        self.client.login(username='student', password='password')
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))


class StudentViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='student', password='password')

    def test_dashboard_view(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'codingapp/dashboard.html')

    def test_module_list_view(self):
        response = self.client.get(reverse('module_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.module.title)

    def test_module_detail_view(self):
        response = self.client.get(reverse('module_detail', args=[self.module.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.module.title)
        self.assertContains(response, self.question.title)

    @patch('codingapp.views.execute_code')
    def test_question_detail_view_and_submission(self, mock_execute_code):
        """
        Test the question detail view and a successful code submission.
        """
        # Mock the response from the Piston API
        mock_execute_code.return_value = ([{
            "status": "Accepted",
            "actual_output": ["1"]
        }], None)

        url = reverse('question_detail', args=[self.question.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.question.title)

        # Test a valid code submission
        response = self.client.post(url, {
            'code': 'print(1)',
            'language': 'python'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Submission.objects.filter(user=self.user, question=self.question, status='Accepted').exists())
        self.assertContains(response, "Accepted")


class AssessmentViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='student', password='password')
        self.assessment = Assessment.objects.create(
            title="Test Assessment",
            duration_minutes=60,
            start_time=timezone.now() - datetime.timedelta(minutes=30),
            end_time=timezone.now() + datetime.timedelta(minutes=30)
        )
        self.assessment.groups.add(self.group)
        self.assessment_question = AssessmentQuestion.objects.create(assessment=self.assessment,
                                                                       question=self.question)
        self.session = AssessmentSession.objects.create(
            user=self.user,
            assessment=self.assessment,
            start_time=timezone.now()
        )

    def test_assessment_list_view(self):
        response = self.client.get(reverse('assessment_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.assessment.title)

    def test_assessment_detail_view(self):
        url = reverse('assessment_detail', args=[self.assessment.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response,
                             reverse('submit_assessment_code', args=[self.assessment.id, self.question.id]))

    @patch('codingapp.views.execute_code')
    def test_submit_assessment_code_view(self, mock_execute_code):
        mock_execute_code.return_value = ([{
            "status": "Accepted",
            "actual_output": ["1"]
        }], None)

        url = reverse('submit_assessment_code', args=[self.assessment.id, self.question.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.assessment.title)

        response = self.client.post(url, {
            'code': 'print(1)',
            'language': 'python'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AssessmentSubmission.objects.filter(user=self.user, assessment=self.assessment,
                                                question=self.question).exists())


class TeacherViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='teacher', password='password')

    def test_teacher_dashboard_view(self):
        response = self.client.get(reverse('teacher_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'codingapp/teacher_dashboard.html')

    def test_teacher_module_list_view(self):
        response = self.client.get(reverse('teacher_module_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.module.title)

    def test_teacher_add_module_view(self):
        response = self.client.post(reverse('add_module'), {
            'title': 'New Module',
            'description': 'A new test module.'
        })
        self.assertRedirects(response, reverse('module_list'))
        self.assertTrue(Module.objects.filter(title='New Module').exists())

    def test_teacher_delete_module_view(self):
        response = self.client.post(reverse('delete_module', args=[self.module.id]))
        self.assertRedirects(response, reverse('module_list'))
        self.assertFalse(Module.objects.filter(id=self.module.id).exists())


class PermissionTests(BaseTestCase):
    def test_student_cannot_access_teacher_dashboard(self):
        self.client.login(username='student', password='password')
        response = self.client.get(reverse('teacher_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirects to login
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('teacher_dashboard')}")

    def test_unauthenticated_user_cannot_access_dashboard(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_student_cannot_access_assessment_not_in_group(self):
        self.client.login(username='student', password='password')
        other_group = Group.objects.create(name="Other Group")
        assessment = Assessment.objects.create(
            title="Other Assessment",
            duration_minutes=60,
            start_time=timezone.now(),
            end_time=timezone.now() + datetime.timedelta(hours=1)
        )
        assessment.groups.add(other_group)
        response = self.client.get(reverse('assessment_detail', args=[assessment.id]))
        self.assertEqual(response.status_code, 403)


class ModelTests(BaseTestCase):
    def test_assessment_is_active(self):
        """Test the is_active method of the Assessment model."""
        now = timezone.now()
        active_assessment = Assessment(start_time=now - datetime.timedelta(hours=1),
                                     end_time=now + datetime.timedelta(hours=1))
        inactive_assessment = Assessment(start_time=now + datetime.timedelta(hours=1),
                                       end_time=now + datetime.timedelta(hours=2))
        self.assertTrue(active_assessment.is_active())
        self.assertFalse(inactive_assessment.is_active())

    def test_user_profile_creation(self):
        """Test that a UserProfile is created automatically when a new User is created."""
        new_user = User.objects.create_user(username='testuser', password='password')
        self.assertTrue(UserProfile.objects.filter(user=new_user).exists())


class QuizTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='student', password='password')
        self.quiz = Quiz.objects.create(title="Test Quiz")
        self.quiz.questions.add(self.mcq_question)
    
    def test_take_quiz_view(self):
        response = self.client.get(reverse('take_quiz', args=[self.quiz.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.quiz.title)

    def test_quiz_submission(self):
        url = reverse('take_quiz', args=[self.quiz.id])
        # Simulate starting the quiz to set the session
        self.client.get(url)
        
        # Now, post the answers
        response = self.client.post(url, {f'question_{self.mcq_question.id}': 'A'})
        
        self.assertEqual(response.status_code, 302) # Should redirect to results
        
        submission = QuizSubmission.objects.get(user=self.user, quiz=self.quiz)
        self.assertEqual(submission.score, 1)
        self.assertTrue(
            QuizAnswer.objects.filter(submission=submission, question=self.mcq_question, selected_option="A").exists())
        self.assertRedirects(response, reverse('quiz_result', args=[submission.id]))


class FormTests(BaseTestCase):
    def test_registration_form(self):
        form_data = {
            'username': 'formuser',
            'email': 'formuser@example.com',
            'password1': 'ComplexPassword123!',
            'password2': 'ComplexPassword123!',
            'full_name': 'Form User',
        }
        form = RegistrationForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_assessment_form(self):
        form_data = {
            'title': 'Form Assessment',
            'duration_minutes': 30,
            'start_time': timezone.now(),
            'end_time': timezone.now() + datetime.timedelta(hours=1),
        }
        form = AssessmentForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_question_form(self):
        form_data = {
            'title': 'Form Question',
            'description': 'A question from a form.',
            'question_type': 'coding',
        }
        form = QuestionForm(data=form_data)
        self.assertTrue(form.is_valid())


class BulkUploadTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='teacher', password='password')

    def test_bulk_user_upload(self):
        # Create a dummy xlsx file
        from io import BytesIO
        import openpyxl
        
        output = BytesIO()
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(['username', 'full_name', 'email', 'password', 'group'])
        sheet.append(['newuser1', 'New User One', 'user1@example.com', 'password123', 'Test Group'])
        workbook.save(output)
        output.seek(0)
        
        file = SimpleUploadedFile("users.xlsx", output.read(),
                                  content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        response = self.client.post(reverse('bulk_user_upload'), {'excel_file': file})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='newuser1').exists())
        self.assertContains(response, 'Users created: 1')

    def test_bulk_mcq_upload(self):
        from io import BytesIO
        import pandas as pd

        df = pd.DataFrame({
            'Question Text': ['What is 2+2?'],
            'Description': ['A simple math question.'],
            'Option1': ['3'],
            'Option2': ['4'],
            'Option3': ['5'],
            'Option4': ['6'],
            'Correct Answer': ['4']
        })
        
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        
        file = SimpleUploadedFile("mcqs.xlsx", output.read(),
                                  content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        response = self.client.post(reverse('teacher_bulk_upload_mcq'), {'excel_file': file})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Question.objects.filter(title='What is 2+2?').exists())

class APITests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='student', password='password')

    @patch('codingapp.views.requests.post')
    def test_run_code_api(self, mock_post):
        # Mock the external API call
        mock_response = mock_post.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "run": {
                "stdout": "hello world",
                "stderr": ""
            }
        }

        response = self.client.post(
            # FIX: The URL name is 'run_code', not 'run_code_view'
            reverse('run_code'),
            data=json.dumps({'code': 'print("hello world")', 'language': 'python'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # This checks if the 'output' key exists and has the correct value
        self.assertIn('output', data)
        self.assertEqual(data['output'], "hello world")