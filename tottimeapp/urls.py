from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('index.html', views.index, name='index'),
  ]
