from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Rule

class SignupForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=False, help_text='Optional.')
    last_name = forms.CharField(max_length=30, required=False, help_text='Optional.')
    email = forms.EmailField(max_length=254, help_text='Required. Inform a valid email address.')
    class Meta:
        model = User 
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

class OrderForm(forms.Form):
    items = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}))

class RuleForm(forms.ModelForm):
    class Meta:
        model = Rule
        fields = ['rule', 'weekly_qty', 'daily', 'break_only', 'am_only', 'lunch_only', 'pm_only']
        widgets = {
            'rule': forms.TextInput(attrs={'class': 'custom-input'}),
        }