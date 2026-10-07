from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "ynav"

urlpatterns = [
    path("", views.home, name="home"),
    path("hello", views.hello, name="hello"),
    path("user/profile", views.profile, name="profile"),
    path("time", views.server_time, name="time"),
    path("query", views.query, name="query"),
    path("query/profile", views.query_profile, name="query_profile"),
    path("query/range", views.query_range, name="query_range"),
    path("form", views.name_form, name="form"),
    path("multiplication", views.multiplication, name="multiplication"),
    path("pakiman", views.pakiman_list, name="pakiman_list"),
    path("pakiman/add", views.pakiman_add, name="pakiman_add"),
    # Bonus : inscription et connexion avec les formulaires de django.contrib.auth
    path("signup", views.signup, name="signup"),
    path(
        "login",
        auth_views.LoginView.as_view(template_name="ynav/login.html"),
        name="login",
    ),
    path("logout", auth_views.LogoutView.as_view(), name="logout"),
]
