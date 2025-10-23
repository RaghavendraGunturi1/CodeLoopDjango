# in codingapp/serializers.py
from rest_framework import serializers
from .models import Question

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        # Define the fields you want to expose in the API
        fields = ['id', 'title', 'description', 'test_cases']