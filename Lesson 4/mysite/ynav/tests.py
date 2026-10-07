import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Pakiman


class StaticPagesTests(TestCase):
    def test_home_links_every_exercise(self):
        response = self.client.get("/ynav/")
        self.assertContains(response, "/ynav/pakiman?level=5")

    def test_root_redirects_to_home(self):
        self.assertRedirects(self.client.get("/"), "/ynav/")

    def test_hello(self):
        self.assertContains(self.client.get("/ynav/hello"), "<h1>Hello World</h1>")

    def test_profile(self):
        response = self.client.get("/ynav/user/profile")
        self.assertContains(response, "<title>Profile</title>")
        self.assertContains(response, "First Name: John")

    def test_time(self):
        response = self.client.get("/ynav/time")
        self.assertRegex(response.content.decode(), r"It is \d{2}:\d{2}")


class QueryParametersTests(TestCase):
    def test_query(self):
        self.assertContains(self.client.get("/ynav/query?p=hello"), "hello")

    def test_query_is_escaped(self):
        response = self.client.get("/ynav/query", {"p": "<b>x</b>"})
        self.assertContains(response, "&lt;b&gt;x&lt;/b&gt;")

    def test_query_without_p(self):
        self.assertContains(self.client.get("/ynav/query"), "No <code>p</code> parameter")

    def test_query_profile(self):
        response = self.client.get("/ynav/query/profile?first_name=John&last_name=Doe")
        self.assertContains(response, "John Doe")

    def test_range(self):
        response = self.client.get("/ynav/query/range?min=1&max=5")
        items = re.findall(r"<li>(\d+)</li>", response.content.decode())
        self.assertEqual(items, ["1", "2", "3", "4", "5"])

    def test_range_invalid(self):
        self.assertContains(self.client.get("/ynav/query/range?min=a&max=5"), "Give two integers")

    def test_range_too_large(self):
        self.assertContains(self.client.get("/ynav/query/range?min=0&max=10000000"), "Range too large")

    def test_range_reversed_is_empty(self):
        self.assertContains(self.client.get("/ynav/query/range?min=5&max=1"), "Empty range")

    def test_multiplication(self):
        response = self.client.get("/ynav/multiplication?n=5")
        self.assertContains(response, "5 x 1 = 5")
        self.assertContains(response, "5 x 10 = 50")
        self.assertNotContains(response, "5 x 11")


class FormTests(TestCase):
    def test_form_get_shows_field(self):
        response = self.client.get("/ynav/form")
        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'class="input"')

    def test_form_post_says_hello(self):
        self.assertContains(self.client.post("/ynav/form", {"name": "John"}), "Hello John")

    def test_form_post_empty_shows_error(self):
        response = self.client.post("/ynav/form", {"name": ""})
        self.assertContains(response, "is-danger")
        self.assertNotContains(response, "Hello ")


class PakimanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Pakiman.objects.create(name="Pikachu", type="Electric", level=12, attack=55)
        Pakiman.objects.create(name="Squirtle", type="Water", level=3, attack=48)
        Pakiman.objects.create(name="Eevee", type="Normal", level=5, attack=45)

    def test_list_all(self):
        response = self.client.get(reverse("ynav:pakiman_list"))
        for name in ["Pikachu", "Squirtle", "Eevee"]:
            self.assertContains(response, name)

    def test_filter_is_strictly_greater(self):
        response = self.client.get("/ynav/pakiman?level=5")
        self.assertContains(response, "Pikachu")
        self.assertNotContains(response, "Squirtle")
        self.assertNotContains(response, "Eevee")

    def test_invalid_level_shows_everything(self):
        response = self.client.get("/ynav/pakiman?level=abc")
        self.assertContains(response, "must be an integer")
        self.assertContains(response, "Squirtle")

    def test_add_redirects_and_saves(self):
        data = {"name": "Mew", "type": "Psychic", "level": 50, "attack": 100}
        response = self.client.post("/ynav/pakiman/add", data)
        self.assertRedirects(response, "/ynav/pakiman")
        self.assertTrue(Pakiman.objects.filter(name="Mew").exists())

    def test_add_rejects_level_zero(self):
        data = {"name": "Bad", "type": "None", "level": 0, "attack": 1}
        response = self.client.post("/ynav/pakiman/add", data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pakiman.objects.filter(name="Bad").exists())


class AuthTests(TestCase):
    def test_signup_logs_in(self):
        data = {"username": "alice", "password1": "S3cure-pass!", "password2": "S3cure-pass!"}
        response = self.client.post("/ynav/signup", data)
        self.assertRedirects(response, "/ynav/")
        self.assertContains(self.client.get("/ynav/"), "alice")

    def test_login_and_logout(self):
        User.objects.create_user("bob", password="S3cure-pass!")
        response = self.client.post("/ynav/login", {"username": "bob", "password": "S3cure-pass!"})
        self.assertRedirects(response, "/ynav/")
        self.assertRedirects(self.client.post("/ynav/logout"), "/ynav/")
        self.assertContains(self.client.get("/ynav/"), "Log in")
