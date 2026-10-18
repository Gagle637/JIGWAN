from django.urls import path

from .views import LoginView, MeDeleteView, RefreshView, RegisterView

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/me", MeDeleteView.as_view(), name="auth-me"),
]
