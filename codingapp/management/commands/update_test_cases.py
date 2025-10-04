# myapp/management/commands/update_test_cases.py
from django.core.management.base import BaseCommand
from codingapp.models import Question

class Command(BaseCommand):
    help = "Updates test cases to the new format where expected_output is a list."

    def handle(self, *args, **kwargs):
        questions = Question.objects.all()
        for question in questions:
            updated_test_cases = []
            for test_case in question.test_cases:
                # Convert expected_output to a list if it's a string
                if isinstance(test_case["expected_output"], str):
                    test_case["expected_output"] = [test_case["expected_output"]]
                updated_test_cases.append(test_case)
            question.test_cases = updated_test_cases
            question.save()
            self.stdout.write(self.style.SUCCESS(f"Updated test cases for question: {question.title}"))