from django.urls import path

from . import views

urlpatterns = [
    path('', views.Members.as_view(), name='members'),
]
