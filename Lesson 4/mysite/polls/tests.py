from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Question


class PollsPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        q = Question.objects.create(question_text="What's up?", pub_date=timezone.now())
        q.choice_set.create(choice_text="Choice 1", votes=2)

    def test_str(self):
        self.assertEqual(str(Question.objects.get()), "What's up?")

    def test_index_lists_questions_and_choices(self):
        response = self.client.get("/polls/")
        self.assertContains(response, "<h1>Questions</h1>", html=False)
        self.assertContains(response, "1 choices")
        self.assertContains(response, "Choice 1 / 2")

    def test_index_escapes_html(self):
        Question.objects.create(question_text="<script>x</script>", pub_date=timezone.now())
        response = self.client.get("/polls/")
        self.assertNotContains(response, "<script>")

    def test_hello(self):
        response = self.client.get("/polls/hello")
        self.assertContains(response, "<h1>Hello World</h1>")

    def test_questions_template(self):
        response = self.client.get(reverse("polls:questions"))
        self.assertTemplateUsed(response, "polls/questions.html")
        self.assertContains(response, "Choice 1 - 2 votes")
