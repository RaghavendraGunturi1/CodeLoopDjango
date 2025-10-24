from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Module, Question, Submission, Assessment, AssessmentQuestion, AssessmentSession, Group, AssessmentSubmission
from unittest.mock import patch
import datetime
from django.utils import timezone

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
        self.assessment_question = AssessmentQuestion.objects.create(assessment=self.assessment, question=self.question)
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
        self.assertRedirects(response, reverse('submit_assessment_code', args=[self.assessment.id, self.question.id]))

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
        self.assertTrue(AssessmentSubmission.objects.filter(user=self.user, assessment=self.assessment, question=self.question).exists())


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


this code solved all the test problems